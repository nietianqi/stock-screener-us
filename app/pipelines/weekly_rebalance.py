from __future__ import annotations

from app.pipelines.daily_scan import DailyScanPipeline, ScanOptions


def run_weekly_rebalance(pipeline: DailyScanPipeline, options: ScanOptions):
    return pipeline.run(options)

