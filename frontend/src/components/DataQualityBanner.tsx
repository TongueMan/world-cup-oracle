interface DataQualityBannerProps {
  message?: string;
}

export function DataQualityBanner({ message }: DataQualityBannerProps) {
  if (!message) return null;

  return (
    <div className="rounded-2xl border border-rose-300/30 bg-rose-400/10 p-4 text-rose-50 shadow-[0_20px_45px_rgba(0,0,0,0.2)]">
      <div className="flex items-start gap-3">
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-rose-200/40 bg-rose-300/15 text-sm font-bold">
          !
        </div>
        <div>
          <div className="text-sm font-semibold">数据通道异常</div>
          <div className="mt-1 text-sm leading-6 text-rose-100/85">{message}</div>
          <div className="mt-2 text-xs text-rose-100/60">
            请确认后端服务在 localhost:8000 运行，或点击“启动严格预测”重新校验。
          </div>
        </div>
      </div>
    </div>
  );
}
