import { useState, useEffect, useCallback } from 'react';
import { api } from '../lib/api';
import type { DataQualityReport, TournamentPrediction } from '../lib/types';

export function usePrediction() {
  const [prediction, setPrediction] = useState<TournamentPrediction | null>(null);
  const [dataStatus, setDataStatus] = useState<DataQualityReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPrediction = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTournament();
      setPrediction(data);
      setDataStatus(data.data_quality_report);
    } catch (err) {
      setPrediction(null);
      setError(err instanceof Error ? err.message : 'Failed to load prediction');
      try {
        const status = await api.getDataStatus();
        setDataStatus(status);
      } catch {
        setDataStatus(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const runPrediction = useCallback(
    async () => {
      setLoading(true);
      setError(null);
      try {
        await api.runPrediction();
        // 给后端留一点时间写入严格预测结果，然后重新读取。
        setTimeout(() => loadPrediction(), 3000);
      } catch (err) {
        setPrediction(null);
        setError(err instanceof Error ? err.message : 'Failed to run prediction');
        try {
          const status = await api.getDataStatus();
          setDataStatus(status);
        } catch {
          setDataStatus(null);
        }
        setLoading(false);
      }
    },
    [loadPrediction],
  );

  useEffect(() => {
    loadPrediction();
  }, [loadPrediction]);

  return { prediction, dataStatus, loading, error, runPrediction, reload: loadPrediction };
}
