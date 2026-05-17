# muduo-core

基于 [muduo](https://github.com/chenshuo/muduo/) 设计思想的精简 **Linux TCP 网络库**：**Reactor + epoll + 线程池**，对外提供 `TcpServer` 与回调接口，用于学习与中小型 TCP 服务原型。

## 功能概览

- **Multi-Reactor**：主 `EventLoop` 负责监听与 `accept`，工作线程池内 **one loop per thread**，新连接轮询分配到各 sub loop。
- **IO 多路复用**：`Poller` / `EPollPoller` 封装 epoll；`Channel` 绑定 fd 与读写关闭回调。
- **连接管理**：`TcpConnection` + `Buffer`（读写缓冲）；`send` / `shutdown` 通过所属 `EventLoop::runInLoop` 保证线程归属。
- **跨线程唤醒**：`eventfd` + `queueInLoop`，向指定 loop 投递任务。
- **示例**：`example/testserver.cc` 为多线程 Echo 服务。

本仓库为个人应用实践向裁剪实现，**不包含**官方 muduo 的 HTTP、Protobuf、异步日志等完整子系统。

## 环境要求

| 项 | 说明 |
|----|------|
| 操作系统 | Linux（依赖 epoll） |
| 编译器 | 支持 **C++11** 的 GCC / Clang |
| 构建 | **CMake** ≥ 3.0 |
| 链接库 | **pthread** |

## 构建

```bash
mkdir -p build && cd build
cmake ..
cmake --build .
```

默认生成共享库 `muduo_core`，示例可执行文件输出在 `example/` 目录（见 `example/CMakeLists.txt` 中的 `RUNTIME_OUTPUT_DIRECTORY`）。

### 生成 `compile_commands.json`（供 clangd / IDE）

```bash
cd build
cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON ..
ln -sf build/compile_commands.json ../compile_commands.json   # 在项目根目录执行时
```

## 运行示例

```bash
./example/testserver
```

默认监听 `0.0.0.0:8080`，多线程 Echo（可在源码中修改 `setThreadNum` 与端口）。

## 目录结构

```
muduo-core/
├── CMakeLists.txt          # 顶层工程
├── include/                # 公共头文件
├── src/                    # 库实现，生成 libmuduo_core
└── example/                # 示例（testserver）
```

## 核心模块

| 模块 | 职责 |
|------|------|
| `EventLoop` | 事件循环：`poll`、分发 `Channel`、runInLoop / queueInLoop |
| `Channel` | fd 与感兴趣事件、回调；与 `TcpConnection` 配合可用 `tie` 延长生命周期 |
| `Poller` / `EPollPoller` | epoll 封装，`updateChannel` / `removeChannel` |
| `EventLoopThread` / `EventLoopThreadPool` | 每线程一个栈上 `EventLoop`，线程池供 `TcpServer` 轮询选用 |
| `Acceptor` | 监听套接字与 `accept`，运行于 base loop |
| `TcpServer` | 组装 Acceptor、线程池与用户回调 |
| `TcpConnection` | 连接状态、`Socket`、`Channel`、输入/输出 `Buffer` |
| `Buffer` | 应用层读写缓冲 |
| `InetAddress` / `Socket` | 地址与套接字封装 |
| `Logger` | 简单同步日志宏 |

## 并发模型简述

1. **主 reactor**：用户线程中的 base `EventLoop` 运行 `Acceptor`，处理 listen fd。
2. **从 reactor**：`setThreadNum(n)` 后启动 `n` 个 `EventLoopThread`，每个线程内一个 `EventLoop::loop()`。
3. 新连接在 `TcpServer::newConnection` 中通过 `getNextLoop()` 选定 `ioLoop`，并以 `ioLoop->runInLoop(&TcpConnection::connectEstablished)` 在 **对应 sub loop 线程** 内向该 loop 的 `Poller` 注册 connfd（如 `enableReading` → `epoll_ctl`）。

## 压测结果

对 `example/testserver`（Multi-Reactor Echo，`setThreadNum(3)`）进行压测。压测前已注释 `onConnection` / `onMessage` 中的 `LOG_INFO`，避免日志 IO 影响结果。

### 测试环境

| 项 | 配置 |
|----|------|
| 服务端 | 2 核 CPU、2 GiB 内存、**公网带宽 1 Mbps**、通用型 SSD 云主机（Ubuntu） |
| 客户端（公网） | Windows 11，Intel i7-12700H，32 GiB 内存 |
| 服务端口 | `0.0.0.0:8080` |
| 压测时长 | 每轮 30 s |
| 压测工具 | Python 脚本 `bench_echo.py`（多线程并发 TCP Echo，统计总往返次数与 **approx_qps**） |

**指标说明：** `approx_qps` = 所有连接在测试时间内的 **往返次数之和 / 墙钟时间**，表示 **全链路总吞吐（次/秒）**，非单连接 QPS。

### 公网压测（PC → 云公网 IP）

| 并发连接 | 消息大小 | 总往返次数 | approx_qps | 说明 |
|----------|----------|------------|------------|------|
| 20 | 64 B | 31,850 | **1,060** | 基准 |
| 50 | 64 B | 29,561 | **938** | 增加连接后 QPS 略降，带宽已饱和 |
| 20 | 256 B | 11,748 | **388** | 包长增大，QPS 明显下降 |

**结论：** 公网场景下吞吐受 **1 Mbps 带宽与 RTT** 制约；提高并发或增大消息长度无法显著提升 QPS。

### 本机回环压测（云主机 `127.0.0.1`，避开公网带宽）

| 并发连接 | 消息大小 | 总往返次数 | approx_qps | 说明 |
|----------|----------|------------|------------|------|
| 50 | 64 B | 862,049 | **28,496** | 约为公网（20 连接、64 B）的 **27 倍** |
| 100 | 64 B | 854,984 | **28,029** | 增加连接后 QPS 基本持平，**CPU 已饱和** |
| 50 | 256 B | 845,483 | **28,009** | 包长增大对 QPS 影响很小 |

**结论：** 本机回环下可验证服务在 **loopback** 上具备更高吞吐；服务端与压测客户端同机共享 CPU，约 **2.8 万** 次往返/秒为当前 2 核环境下的参考上限。

### 简要对比

```
公网 1 Mbps（64 B, 20 连接）  ≈ 1.0k  往返/秒  →  带宽瓶颈
本机回环（64 B, 50 连接）     ≈ 28k   往返/秒  →  CPU 瓶颈（同机压测）
```

复现压测可使用多线程 TCP Echo 脚本（将 `HOST` 设为公网 IP 或 `127.0.0.1`，并按场景调整 `CONNS`、`MSG`、`DURATION`）。

## 参考

- 官方 muduo：<https://github.com/chenshuo/muduo/>
- 《Linux 多线程服务端编程：使用 muduo C++ 网络库》，陈硕
- 《Linux 高性能服务器编程》，游双
