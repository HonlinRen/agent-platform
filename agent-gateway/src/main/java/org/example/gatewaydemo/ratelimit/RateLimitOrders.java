package org.example.gatewaydemo.ratelimit;

/**
 * GlobalFilter 执行顺序（数值越小越先执行）。
 * 顺序：RPM → TPM 输入（读 body）→ TPM 输出（装饰响应流）。
 */
public final class RateLimitOrders {

    /** Correlation / request id（最早执行，在 JWT 之前） */
    public static final int CORRELATION_ID = -5;
    /** JWT 租户绑定（在 RPM 之前） */
    public static final int JWT_TENANT = -4;
    /** 每分钟请求数，全路径生效 */
    public static final int RPM = -3;
    /** 每分钟输入 token，仅 LLM 路径；需缓存并回放请求体 */
    public static final int TPM_INPUT = -2;
    /** 每分钟输出 token，仅 LLM 路径；在响应写出时按 chunk 扣减 */
    public static final int TPM_OUTPUT = -1;

    private RateLimitOrders() {
    }
}
