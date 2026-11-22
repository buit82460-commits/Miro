"""Studio FX: pure ffmpeg-filter builders ported from dubtool (read-only source).

Nguon dubtool (chi doc, khong import):
- core/studio_filters.py (visual_filters, _source_alpha, overlay_position)
- core/studio_model.py dong 17-31 (hang so TRANSFORM/EFFECTS/TRANSITIONS/MASK/CHROMA/AUDIO_MIX/BLENDS)
- core/studio_curves.py (EASES, _ease, curve_expression)
- core/ffmpeg_utils.py (atempo_chain)

Chi dung stdlib. Moi ham la thuan tuy (dict in -> str out), khong import miro.
"""

EFFECTS = {
    "brightness": 0.0,
    "contrast": 1.0,
    "saturation": 1.0,
    "blur": 0.0,
    "grayscale": False,
    "vignette": False,
    "temperature": 0.0,
    "noise": 0.0,
    "sharpen": 0.0,
    "rgb_split": 0.0,
    "glitch": 0.0,
    "vhs": 0.0,
    "glow": 0.0,
}
# NOTE: `glow` khong co trong dubtool (studio_model.py dong 19-22 khong
# dinh nghia) — render bang gblur + blend screen (ffmpeg chuan).

TRANSFORM_DEFAULTS = {
    "x": 0.5,
    "y": 0.5,
    "scale": 1.0,
    "rotation": 0,
    "flip_h": False,
    "flip_v": False,
    "fit": "contain",
}
# Nguon: studio_model.py dong 17-18 (TRANSFORM).

TRANSITIONS = (
    "fade",
    "wipe_left",
    "wipe_right",
    "wipe_up",
    "wipe_down",
    "slide_left",
    "slide_right",
    "slide_up",
    "slide_down",
    "circle_open",
)
# Nguon: studio_model.py dong 27 (TRANSITIONS, copy day du de validate).

MASK_TYPES = ("none", "rectangle", "ellipse")
# Nguon: studio_model.py dong 288 (mask shape cho phep).

BLENDS = ("normal", "multiply", "screen", "overlay", "addition", "difference")
# Nguon: studio_model.py dong 28 (BLENDS).

AUDIO_MIX_DEFAULTS = {
    "ducking": False,
    "duck_db": -12,
    "threshold_db": -35,
    "attack": 0.03,
    "release": 0.3,
    "lufs": None,
}
# Nguon: studio_model.py dong 30 (AUDIO_MIX).

_CHROMA_NAMED = {
    "black": "000000",
    "transparent": "000000",
    "white": "FFFFFF",
    "red": "FF0000",
    "yellow": "FFFF00",
    "cyan": "00FFFF",
    "lime": "00FF00",
    "blue": "0000FF",
    "orange": "FFA500",
}


def _alpha(inside: str) -> str:
    """Nguon: studio_filters.py dong 7-9 (_alpha_filter)."""
    return f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({inside})'"


def effect_filter(name: str, params: dict) -> str:
    """Tra filter ffmpeg cho mot effect don.

    Nguon: studio_filters.py dong 82-119 (visual_filters, khoi effect).
    `params` la dict effect day du (kieu clip["effects"]); `name` chon truong.
    `glow` khong co trong dubtool — render bang gblur + blend screen
    (ffmpeg chuan). Chuoi glow chua placeholder `[IN]`/`[OUT]` (multi-statement
    split/blend); caller thay `[IN]`->`[cur]`, `[OUT]`->`[v{step}]` truoc khi rap.
    """
    p = params or {}
    if name == "brightness":
        return f"eq=brightness={float(p.get('brightness', 0))}"
    if name == "contrast":
        return f"eq=contrast={float(p.get('contrast', 1))}"
    if name == "saturation":
        return f"eq=saturation={float(p.get('saturation', 1))}"
    if name == "grayscale":
        # Nguon dong 84: grayscale = saturation 0.
        return "eq=saturation=0"
    if name == "blur":
        # Nguon dong 87-88.
        return f"gblur=sigma={float(p.get('blur', 0))}"
    if name == "vignette":
        # Nguon dong 89-90.
        return "vignette=PI/5"
    if name == "temperature":
        # Nguon dong 91-94: warm/cool RGB balance don gian.
        t = float(p.get("temperature", 0))
        return f"colorchannelmixer=rr={1 + t * .25}:bb={1 - t * .25}"
    if name == "noise":
        # Nguon dong 95-97.
        s = round(float(p.get("noise", 0)))
        return f"format=gbrap,noise=c0s={s}:c1s={s}:c2s={s}:c3s=0:allf=t+u:all_seed=23"
    if name == "sharpen":
        # Nguon dong 98-99.
        return (
            f"unsharp=luma_msize_x=5:luma_msize_y=5"
            f":luma_amount={float(p.get('sharpen', 0))}:chroma_amount=0:alpha_amount=0"
        )
    if name in ("rgb_split", "glitch", "vhs"):
        # Nguon dong 110-119 (geq rgb_split/glitch/vhs).
        split = float(p.get("rgb_split", 0))
        glitch = float(p.get("glitch", 0))
        vhs = float(p.get("vhs", 0))
        shift = f"{glitch * 24:.9g}*gte(sin(floor(Y/8)*13+floor(T*12)*7),0.5)*sin(T*40+Y/9)"
        scan = f"(1-{vhs * .18:.9g}*mod(floor(Y),2))"
        return (
            "format=rgba,"
            f"geq=r='r(clip(X+({shift})-{split},0,W-1),Y)*{scan}':"
            f"g='g(clip(X+({shift}),0,W-1),Y)*{scan}':"
            f"b='b(clip(X+({shift})+{split},0,W-1),Y)*{scan}':a='alpha(X,Y)'"
        )
    if name == "glow":
        s = max(0.1, min(2.0, float(p.get("glow", 0) or 0.6)))
        op = min(0.9, 0.3 + s * 0.3)
        # Multi-statement: caller thay [IN]->[cur], [OUT]->[v{step}].
        return (f"[IN]split=2[gin][gtmp];[gtmp]gblur=sigma={s * 4:.3g}[gblur];"
                f"[gin][gblur]blend=all_mode=screen:all_opacity={op:.3g}[OUT]")
    if name == "chroma_key":
        color = str(p.get("color", "0x00FF00") or "0x00FF00").removeprefix("0x")
        sim = max(0.0, min(1.0, float(p.get("similarity", 0.1))))
        blend = max(0.0, min(1.0, float(p.get("blend", 0.05))))
        return f"chromakey=0x{color}:{sim:.3g}:{blend:.3g}"
    raise ValueError(f"effect khong ho tro: {name}")


def color_filter(adj: dict) -> str:
    """Ghep brightness/contrast/saturation/temperature/curves/lut3d.

    Nguon: studio_filters.py dong 82-86 (eq), 91-94 (temperature),
    dong 100-109 (curves, lut3d).
    `adj` co the chua: brightness, contrast, saturation, temperature,
    curves {master,red,green,blue: [{x,y}]}, lut3d (duong dan file .cube).
    Tra chuoi filter (nhieu filter noi bang dau phay), rong neu khong co gi.
    """
    adj = adj or {}
    out = []
    b, c, s = adj.get("brightness", 0), adj.get("contrast", 1), adj.get("saturation", 1)
    if b != 0 or c != 1 or s != 1:
        out.append(f"eq=brightness={b}:contrast={c}:saturation={s}")
    t = adj.get("temperature", 0)
    if t:
        out.append(f"colorchannelmixer=rr={1 + t * .25}:bb={1 - t * .25}")
    curves = adj.get("curves", {})
    opts = []
    for key in ("master", "red", "green", "blue"):
        if curves.get(key):
            pts = " ".join(f"{pt['x']:.9g}/{pt['y']:.9g}" for pt in curves[key])
            opts.append(f"{key}='{pts}'")
    if opts:
        out.append("curves=" + ":".join(opts))
    lut = adj.get("lut3d")
    if lut:
        out.append(f"lut3d=file='{lut}':interp=tetrahedral")
    return ",".join(out)


def transform_filter(t: dict, w: int, h: int) -> str:
    """Ghep x/y/scale/rotation/flip_h/flip_v/fit/crop/opacity thanh filter.

    Nguon: studio_filters.py dong 40-81 (crop, rotate, flip, scale fit),
    dong 120-125 (opacity), dong 143-149 (overlay_position: x/y la toa do
    overlay chu khong phai filter -> ham nay khong tieu thu x/y, caller
    dung x/y de dat overlay).
    `t` co the chua them: crop {x,y,width,height} (ty le 0-1), opacity.
    """
    t = t or {}
    out = []
    crop = t.get("crop", {})
    if crop and any(crop.get(k, d) != d for k, d in (("x", 0), ("y", 0), ("width", 1), ("height", 1))):
        out.append(
            f"crop=w=in_w*{crop.get('width', 1)}:h=in_h*{crop.get('height', 1)}"
            f":x=in_w*{crop.get('x', 0)}:y=in_h*{crop.get('y', 0)}"
        )
    rotation = float(t.get("rotation", 0))
    if rotation == 90:
        # Nguon dong 55-57.
        out.append("transpose=clock")
    elif abs(rotation) == 180:
        # Nguon dong 58-59.
        out.extend(["hflip", "vflip"])
    elif rotation in (270, -90):
        # Nguon dong 60-62.
        out.append("transpose=cclock")
    elif rotation:
        import math

        # Nguon dong 63-67.
        r = math.radians(rotation)
        out.append(
            f"format=rgba,rotate=a={r:.12g}:ow='ceil(rotw({r:.12g})/2)*2'"
            f":oh='ceil(roth({r:.12g})/2)*2':c=black@0"
        )
    if t.get("flip_h"):
        # Nguon dong 68-69.
        out.append("hflip")
    if t.get("flip_v"):
        # Nguon dong 70-71.
        out.append("vflip")
    scale = float(t.get("scale", 1))
    fit = t.get("fit", "contain")
    # Nguon dong 72-78: contain dung min, cover dung max; giu ty le, chan.
    op = "max" if fit == "cover" else "min"
    out.append(
        f"scale=w='max(2,trunc({op}({w}/iw,{h}/ih)*iw*{scale}/2)*2)'"
        f":h='max(2,trunc({op}({w}/iw,{h}/ih)*ih*{scale}/2)*2)':eval=frame"
    )
    opacity = float(t.get("opacity", 1))
    if opacity != 1:
        # Nguon dong 125.
        out.append(f"colorchannelmixer=aa={opacity}")
    return ",".join(out)


def transition_filter(name: str, duration: float) -> str:
    """Tra filter alpha-transition cho clip mo dau (clock T cuc bo).

    Nguon: studio_filters.py dong 131-139 (wipe_*/circle_open qua _alpha_filter);
    fade qua fade=t=in (dong 127-128).
    fade/wipe_left/right/up/down/circle_open (alpha mo dau clip, da xac minh).
    slide_* (truot anh vao khung + fade alpha, ffmpeg chuan, multi-statement
    [IN]/[OUT] nhu glow).
    """
    seconds = float(duration)
    if name == "fade":
        return f"fade=t=in:st=0:d={seconds}:alpha=1"
    if seconds and name.startswith("wipe_"):
        # Nguon dong 133-137.
        progress = f"min(T/{seconds},1)"
        reveal = {
            "wipe_left": f"gte(X/W,1-({progress}))",
            "wipe_right": f"lte(X/W,({progress}))",
            "wipe_up": f"gte(Y/H,1-({progress}))",
            "wipe_down": f"lte(Y/H,({progress}))",
        }.get(name)
        if reveal is None:
            raise ValueError(f"transition khong ho tro: {name}")
        return _alpha(reveal)
    if seconds and name == "circle_open":
        # Nguon dong 138-139.
        return _alpha(f"lte(pow(X/W-.5,2)+pow(Y/H-.5,2),pow(min(T/{seconds},1),2)/2)")
    if seconds and name in ("slide_left", "slide_right", "slide_up", "slide_down"):
        # Render that: overlay chinh stream len nen split, x/y chay theo T
        # (ffmpeg chuan, multi-statement nhu glow: caller thay [IN]/[OUT]).
        p = f"min(T/{seconds},1)"
        pos = {
            "slide_left": f"x='W*(1-{p})':y=0",
            "slide_right": f"x='-W*(1-{p})':y=0",
            "slide_up": f"x=0:y='H*(1-{p})'",
            "slide_down": f"x=0:y='-H*(1-{p})'",
        }[name]
        return (f"[IN]split=2[st][mv];[mv]format=rgba,"
                f"fade=t=in:st=0:d={seconds}:alpha=1[mvf];"
                f"[st][mvf]overlay={pos}[OUT]")
    raise ValueError(f"transition khong ho tro: {name}")


def mask_alpha(mask: dict) -> str:
    """Tra filter alpha geq cho mask rectangle/ellipse/invert + chroma colorkey.

    Nguon: studio_filters.py dong 7-9 (_alpha_filter) + dong 12-34 (_source_alpha).
    `mask` co the chua: shape (none/rectangle/ellipse), x, y, width, height,
    invert, chroma {enabled, color, similarity, blend}.
    Tra "" neu khong co mask/chroma nao kich hoat.
    """
    mask = mask or {}
    factors = []
    shape = mask.get("shape", "none")
    if shape != "none":
        # Nguon dong 16-23.
        x, y = mask.get("x", .5), mask.get("y", .5)
        wdt, hgt = mask.get("width", 1), mask.get("height", 1)
        if shape == "ellipse":
            inside = f"lte(pow((X/W-{x})/{wdt / 2},2)+pow((Y/H-{y})/{hgt / 2},2),1)"
        else:
            inside = f"lte(abs(X/W-{x}),{wdt / 2})*lte(abs(Y/H-{y}),{hgt / 2})"
        factors.append(f"1-({inside})" if mask.get("invert") else inside)
    chroma = mask.get("chroma", {})
    if chroma.get("enabled"):
        # Nguon dong 24-33.
        value = chroma.get("color", "0x00FF00")
        value = _CHROMA_NAMED.get(value, value.removeprefix("0x"))
        red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
        distance = f"sqrt(pow(r(X,Y)-{red},2)+pow(g(X,Y)-{green},2)+pow(b(X,Y)-{blue},2))/441.67295593"
        similarity, blend = chroma.get("similarity", .1), chroma.get("blend", .05)
        factors.append(
            f"clip((({distance})-{similarity})/{blend},0,1)"
            if blend else f"gt(({distance}),{similarity})"
        )
    if not factors:
        return ""
    return _alpha("*".join(f"({f})" for f in factors))


def speed_filter(speed: float) -> str:
    """Tra chuoi atempo cho speed 0.25-4 (audio theo video).

    Nguon: logic copy tu ffmpeg_utils.py dong 16-27 (atempo_chain);
    bien speed gioi han 0.25-4 theo studio_model.py dong 245.
    """
    s = float(speed)
    if not 0.25 <= s <= 4:
        raise ValueError("speed phai trong khoang 0.25-4.")
    parts = []
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.6g}")
    return ",".join(parts)


def _ease_expr(value: str, mode: str) -> str:
    """Nguon: studio_curves.py dong 21-28 (_ease_expression)."""
    if mode == "ease_in":
        return f"(({value})*({value}))"
    if mode == "ease_out":
        return f"(1-(1-({value}))*(1-({value})))"
    if mode == "ease_in_out":
        return f"(({value})*({value})*(3-2*({value})))"
    return f"({value})"


def keyframe_expr(points: list, ease: str = "linear") -> str:
    """Bieu thuc noi suy keyframe theo thoi gian (clock t).

    Port don gian cua curve_expression (studio_curves.py dong 52-66):
    ho tro linear + ease in/out (/in_out); moi point {t, value},
    `ease` mac dinh ap cho moi doan (co the ghi de bang point["ease"]).
    Khong ho tro ease_start/ease_end (sau split) — chi noi suy thuan.
    """
    pts = list(points or [])
    if not pts:
        raise ValueError("points rong.")
    if len(pts) == 1:
        return f"{float(pts[0]['value']):.12g}"
    for pt in pts:
        mode = pt.get("ease", ease)
        if mode not in ("linear", "ease_in", "ease_out", "ease_in_out"):
            raise ValueError(f"ease khong ho tro: {mode}")
    expr = f"{float(pts[-1]['value']):.12g}"
    for left, right in reversed(list(zip(pts, pts[1:]))):
        ratio = f"(((t)-{float(left['t']):.12g})/{float(right['t']) - float(left['t']):.12g})"
        mode = left.get("ease", ease)
        eased = _ease_expr(ratio, mode)
        value = f"({float(left['value']):.12g}+({float(right['value']) - float(left['value']):.12g})*({eased}))"
        expr = f"if(lt((t),{float(right['t']):.12g}),{value},{expr})"
    return f"if(lt((t),{float(pts[0]['t']):.12g}),{float(pts[0]['value']):.12g},{expr})"
