import { ChartNoAxesCombined, DatabaseZap, Home, RefreshCw } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import type { WorldCupSyncStatus } from '../lib/types';

interface AppHeaderProps {
  syncStatus: WorldCupSyncStatus | null;
  syncing?: boolean;
  onSync?: () => void;
}

export function AppHeader({ syncStatus, syncing = false, onSync }: AppHeaderProps) {
  const statusText = syncStatus?.last_status === 'success'
    ? '已更新'
    : syncStatus?.last_status === 'partial'
      ? '部分更新'
      : '待更新';

  return (
    <header className="app-header border-b border-white/12 bg-[#061208]/96 backdrop-blur-xl">
      <div className="header-inner mx-auto flex max-w-7xl items-center gap-4 px-4 sm:px-6 lg:px-8">
        <NavLink to="/" className="brand-link flex min-w-0 items-center gap-3" aria-label="返回首页">
          <div className="football-icon shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-xl font-black sm:text-2xl">世界杯冠军预测智能体</h1>
              <span className="hidden rounded border border-emerald-200/35 bg-emerald-300/14 px-2 py-1 text-xs font-bold text-emerald-50 sm:inline">
                {statusText}
              </span>
            </div>
            <p className="mt-1 hidden truncate text-xs text-white/58 md:block">
              Bing 体育赛程 · 最近更新：{formatDateTime(syncStatus?.last_success_at) || '暂无'}
            </p>
          </div>
        </NavLink>

        <nav className="header-route-nav ml-auto flex shrink-0 items-center gap-1" aria-label="主导航">
          <NavLink to="/" end className={({ isActive }) => `header-route-link ${isActive ? 'active' : ''}`} title="首页">
            <Home size={18} aria-hidden="true" />
            <span className="hidden lg:inline">首页</span>
          </NavLink>
          <NavLink to="/predictions" className={({ isActive }) => `header-route-link ${isActive ? 'active' : ''}`} title="预测中心">
            <ChartNoAxesCombined size={19} aria-hidden="true" />
            <span className="desktop-prediction-label">预测中心</span>
            <span className="mobile-prediction-label">预测</span>
          </NavLink>
        </nav>

        {onSync && (
          <button type="button" onClick={onSync} disabled={syncing} className="header-sync-button" title="更新赛程数据">
            {syncing ? <RefreshCw className="animate-spin" size={18} /> : <DatabaseZap size={18} />}
            <span className="hidden sm:inline">{syncing ? '更新中' : '更新赛程数据'}</span>
          </button>
        )}
      </div>
    </header>
  );
}

function formatDateTime(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}
