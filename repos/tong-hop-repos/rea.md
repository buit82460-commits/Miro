# rea (Reverse Engineer Anything)

> One MCP for reverse engineering across binaries, applications, and runtime behavior.

- **Nguồn:** `research/repos/rea` (npm `rea-agents` v6.8.0)
- **Bản chất:** CLI + MCP server để reverse engineer từ terminal/agent: binary, Electron/JS, firmware, mobile, browser bundle...
- **Chạy local-only**, giữ Evidence provenance + session semantics qua CLI/MCP.

```bash
npx rea-agents setup
```

## Làm được gì

- Phân tích native binary (Ghidra bridge read-only/ephemeral DB, Hopper, Cutter, IDA read-only, Kuna...).
- JS/Electron/Web bundle, runtime observation, network capture (mitmproxy, HAR, QUIC/qlog).
- Firmware (UF2, ESP, devicetree), Android (apktool, jadx, JEB), Harmony, WASM, EVM/Solidity, .NET/IL2CPP, Go binary, Bun standalone.
- Bridge sẵn trong `bridge/`: hopper, cutter, ghidra, android, mitmproxy, pwntools, pwndbg, lldb tracer...
- Skill agent: `.agents/skills/reverse-engineer-anything/`, catalog MCP tool có kiểm chứng.

## Dev

```bash
npm ci
npm run build:cached
npm run test:local -- <path>
npm run check:fast
npm run docs:check
```

Toolchain pin theo `.nvmrc` + `packageManager` (npm 11.16.0, Node ^22/24/26).
