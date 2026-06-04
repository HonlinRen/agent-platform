package org.example.gatewaydemo.ratelimit;

import org.springframework.web.server.ServerWebExchange;

public final class AdminPathSupport {

    private AdminPathSupport() {
    }

    public static boolean isAdminPath(ServerWebExchange exchange) {
        String path = exchange.getRequest().getURI().getPath();
        return path != null && path.startsWith("/admin/");
    }

    /** 健康检查不计入 RPM，避免前端切换租户时占用聊天配额 */
    public static boolean isProbePath(ServerWebExchange exchange) {
        String path = exchange.getRequest().getURI().getPath();
        return "/health".equals(path);
    }

    public static boolean skipRateLimit(ServerWebExchange exchange) {
        return isAdminPath(exchange) || isProbePath(exchange);
    }
}
