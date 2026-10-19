import React from 'react';
import { Link } from 'react-router-dom';
import { 
  usePortfolioSummary, 
  useMarketSentiment, 
  useRiskMetrics, 
  useInvestmentInsights 
} from '../../investments/hooks/useInvestments';
import { Skeleton } from '../../../components/ui/Skeleton';
import { Wallet, TrendingUp, Shield, Cpu, ChevronRight } from 'lucide-react';
import { Badge } from '../../../components/ui/Badge';

export const InvestmentSnapshot: React.FC = () => {
  const { data: summary, isLoading: isLoadingSummary } = usePortfolioSummary();
  const { isLoading: isLoadingSentiment } = useMarketSentiment();
  const { data: risk, isLoading: isLoadingRisk } = useRiskMetrics();
  const { data: insights, isLoading: isLoadingInsights } = useInvestmentInsights();

  const isLoading = isLoadingSummary || isLoadingSentiment || isLoadingRisk || isLoadingInsights;

  if (isLoading) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  const topInsight = insights?.[0];

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
      <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
        <h2 className="font-semibold text-slate-900 flex items-center gap-2">
          <Wallet className="w-5 h-5 text-indigo-600" />
          Investment Intelligence
        </h2>
        <Link to="/app/investments" className="text-sm font-medium text-indigo-600 hover:text-indigo-700 flex items-center">
          Hub <ChevronRight className="w-4 h-4 ml-0.5" />
        </Link>
      </div>

      <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div>
          <p className="text-xs text-slate-500 font-medium mb-1">Portfolio Value</p>
          <p className="text-lg font-bold text-slate-900">
            ${Number(summary?.totalValue ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500 font-medium mb-1">Today's P&L</p>
          <p className={`text-lg font-bold flex items-center gap-1 ${Number(summary?.todaysPnl ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
            {Number(summary?.todaysPnl ?? 0) >= 0 ? <TrendingUp className="w-4 h-4" /> : null}
            {Number(summary?.todaysPnl ?? 0) >= 0 ? '+' : ''}${Number(summary?.todaysPnl ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500 font-medium mb-1 flex items-center gap-1">
            <Shield className="w-3 h-3 text-slate-400" /> Risk Level
          </p>
          <Badge variant={risk?.riskLevel === 'Low' ? 'success' : risk?.riskLevel === 'High' ? 'error' : 'warning'}>
            {risk?.riskLevel}
          </Badge>
        </div>
        <div>
          <p className="text-xs text-slate-500 font-medium mb-1 flex items-center gap-1">
            <Cpu className="w-3 h-3 text-slate-400" /> Top Insight
          </p>
          {topInsight ? (
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-bold text-slate-900">{topInsight.ticker}</span>
              <span className={`text-xs font-semibold ${topInsight.analysis.overallSignal === 'Positive' ? 'text-emerald-600' : 'text-slate-500'}`}>
                {topInsight.analysis.overallSignal} ({topInsight.analysis.confidence}%)
              </span>
            </div>
          ) : (
            <span className="text-sm text-slate-500">None</span>
          )}
        </div>
      </div>
    </div>
  );
};
