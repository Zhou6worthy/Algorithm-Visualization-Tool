"""轻量 CaseRunStore：保存 TestCaseSpec 与多次 CaseRun，并跟踪当前选择。"""
from __future__ import annotations

from ..protocol.cases import CaseRun, TestCaseSpec


class CaseStoreError(RuntimeError):
    pass


class CaseRunStore:
    def __init__(self) -> None:
        self._cases: dict[str, TestCaseSpec] = {}
        self._runs: dict[str, CaseRun] = {}
        self._current_run_id: str | None = None

    # ------------------------------------------------------------------ 写入
    def add_case(self, case: TestCaseSpec) -> None:
        if case.case_id in self._cases:
            raise CaseStoreError(f"case_id 已存在：{case.case_id}")
        self._cases[case.case_id] = case

    def add_run(self, run: CaseRun) -> None:
        if run.case_id not in self._cases:
            raise CaseStoreError(f"run 引用了不存在的 case：{run.case_id}")
        if run.run_id in self._runs:
            raise CaseStoreError(f"run_id 已存在：{run.run_id}")
        self._runs[run.run_id] = run
        if self._current_run_id is None:
            self._current_run_id = run.run_id

    # ------------------------------------------------------------------ 查询
    @property
    def current_case_id(self) -> str | None:
        run = self.current_run
        return run.case_id if run is not None else None

    @property
    def current_run(self) -> CaseRun | None:
        if self._current_run_id is None:
            return None
        return self._runs[self._current_run_id]

    def get_case(self, case_id: str) -> TestCaseSpec:
        try:
            return self._cases[case_id]
        except KeyError as exc:
            raise CaseStoreError(f"不存在 case_id：{case_id}") from exc

    def get_run(self, run_id: str) -> CaseRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise CaseStoreError(f"不存在 run_id：{run_id}") from exc

    def runs_for_case(self, case_id: str) -> list[CaseRun]:
        self.get_case(case_id)
        return [run for run in self._runs.values() if run.case_id == case_id]

    def select_run(self, run_id: str) -> CaseRun:
        run = self.get_run(run_id)
        self._current_run_id = run_id
        return run

    def select_case(self, case_id: str) -> CaseRun:
        runs = self.runs_for_case(case_id)
        if not runs:
            raise CaseStoreError(f"case 尚未执行，没有可切换的 CaseRun：{case_id}")
        return self.select_run(runs[-1].run_id)

    @property
    def case_ids(self) -> list[str]:
        return list(self._cases)

    @property
    def run_ids(self) -> list[str]:
        return list(self._runs)

    def latest_pairs(self) -> list[tuple[TestCaseSpec, CaseRun]]:
        """按 case 添加顺序返回 (spec, 最近一次 run)，供课堂 deck 装配。"""
        pairs: list[tuple[TestCaseSpec, CaseRun]] = []
        for case_id, spec in self._cases.items():
            runs = self.runs_for_case(case_id)
            if runs:
                pairs.append((spec, runs[-1]))
        return pairs

    @property
    def case_count(self) -> int:
        return len(self._cases)

    @property
    def run_count(self) -> int:
        return len(self._runs)
