# muduo-core

基于 [muduo](https://github.com/chenshuo/muduo/) 设计思想的精简 **Linux TCP 网络库**：**Reactor + epoll + 线程池**，对外提供 `TcpServer` 与回调接口，用于学习与中小型 TCP 服务原型。

## 功能概览

- **Multi-Reactor**：主 `EventLoop` 负责监听与 `accept`，工作线程池内 **one loop per thread**，新连接轮询分配到各 sub loop。
- **IO 多路复用**：`Poller` / `EPollPoller` 封装 epoll；`Channel` 绑定 fd 与读写关闭回调。
- **连接管理**：`TcpConnection` + `Buffer`（读写缓冲）；`send` / `shutdown` 通过所属 `EventLoop::runInLoop` 保证线程归属。
- **跨线程唤醒**：`eventfd` + `queueInLoop`，向指定 loop 投递任务。
- **示例**：`example/testserver.cc` 为多线程 Echo 服务。

本仓库为个人即时应用实践向裁剪实现，**不包含**官方 muduo 的 HTTP、Protobuf、异步日志等完整子系统。

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

## 参考

- 官方 muduo：<https://github.com/chenshuo/muduo/>
- 《Linux 多线程服务端编程：使用 muduo C++ 网络库》，陈硕
- 《Linux 高性能服务器编程》，游双

## 26.5.16
## 压测的初步计划及步骤规划
1. 压测前关掉「每条连接都打日志」
onConnection 里对每个连接 LOG_INFO，高并发下磁盘/控制台会成为主要瓶颈，测出来的 QPS 会失真。压测时建议注释或改成极低频日志，再重新编译。
2. 用 Python 快速验证（示例思路）
在 Linux/WSL 上装 Python 3 后，可用 asyncio 开多个协程，每个里 open_connection，循环 write / readexactly。把「并发连接数、每连接请求数、payload 长度」做成参数，跑完打印总耗时和 QPS。