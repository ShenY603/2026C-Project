#include <stdlib.h>

#include "Poller.h"
#include "EPollPoller.h"

Poller *Poller::newDefaultPoller(EventLoop *loop)
{
    if (::getenv("MUDUO_USE_POLL"))
    {
        return nullptr; // 生成poll的实例，根本就没有实现，因为我在重写muduo
    }
    else
    {
        return new EPollPoller(loop); // 生成epoll的实例
    }
}