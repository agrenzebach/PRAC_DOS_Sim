#!/usr/bin/env python3
"""
PRAC Denial of Service simulator for DRAM ACTIVATEs with GLOBAL ALERT stalls.

Supports two modes:
- report:  Uses DRAM timings specific to the selected DRAM type (e.g., 'ddr5').
- explore: DRAM timings are passed via command-line flags.

Behavior:
- Round-robin ACTIVATEs across N rows.
- Each ACTIVATE consumes tRC time.
- tFAW constraint: Maximum 4 ACTIVATEs allowed in any tFAW time window.
- Each ACTIVATE increments a per-row counter.
- If a counter strictly exceeds the threshold, raise an ALERT:
    * ALERT duration is consumed immediately (GLOBAL STALL).
    * No ACTIVATEs (to ANY row) occur while ALERT time is being consumed.
- Record total time each row spent in ALERT state.
- Supports time inputs with units: ns, us (or µs), ms, s.

Common parameters (both modes):
- --rows           Number of rows to operate on.
- --threshold      Counter threshold; ALERT raised when counter > threshold.
- --rfmfreqmin     RFM window start time (e.g., '32us', '64us'). Use '0' to disable RFM.
- --rfmfreqmax     RFM window end time (e.g., '48us', '80us'). Must be >= rfmfreqmin and < 2×rfmfreqmin. Use '0' to disable RFM.
- --randreset      Range for random counter reset (0 to randreset). Default is 0 (always reset to 0).
- --seed           Seed for random number generator. Default is 0.
- --wkld           Workload type: 'rr' (round-robin), 'feinting', or 'mixed:<feint_pct>'. Default is 'rr'.

Inputs (report mode):
- --dram-type      DRAM type (e.g., 'ddr5') for loading protocol parameters from config.

Inputs (explore mode):
- --trc            tRC per ACTIVATE (e.g., '45ns', '3.2us', '64ms', '0.001s').
- --tfaw           tFAW timing constraint for 4 activates window (e.g., '20ns', '25ns'). Default is 20ns.
- --rfmabo         Number of RFMs issued in response to ABO.
- --trfcrfm        tRFC RFM time duration consumed when RFM is issued (e.g., '100ns', '1us'). Use '0' for no time consumption.
- --isoc           Number of ACTIVATEs issued after alert but before reactive RFMs (default 0).
- --abo_delay      ABO delay value (0 to 3). Default is 0.
- --runtime        Total simulation runtime (default 32 ms).

Notes:
- tFAW constraint enforces that no more than 4 ACTIVATEs can occur within any tFAW time window.
- ALERT time is a GLOBAL STALL: while an alert is active, no ACTIVATEs occur.
- ALERT starts immediately after the ACTIVATE that triggered it.
- If remaining runtime is shorter than the alert duration, only the remaining time is consumed and counted.
"""

import random
from typing import List

from cli import parse_and_validate_args
from utils import human_time, is_float_zero


class DRAMSimulator:
    def __init__(
        self,
        rows: int,
        trc_s: float,
        threshold: int,
        rfmabo: int,
        runtime_s: float = 0.032,
        rfm_freq_min_s: float = 0.0,
        rfm_freq_max_s: float = 0.0,
        trfcrfm_s: float = 0.0,
        tfaw_s: float = 20e-9,
        isoc: int = 0,
        randreset: int = 0,
        abo_delay: int = 0,
        wkld: str = "rr",
        # Original string arguments for CSV output
        trc_str: str = "",
        rfmfreqmin_str: str = "",
        rfmfreqmax_str: str = "",
        trfcrfm_str: str = "",
        tfaw_str: str = "",
        runtime_str: str = "",
    ):
        # Validate inputs
        if rows <= 0:
            raise ValueError("rows must be > 0")
        if trc_s <= 0:
            raise ValueError("tRC must be > 0")
        if threshold < 0:
            raise ValueError("threshold must be >= 0")
        if rfmabo < 0:
            raise ValueError("rfmabo must be >= 0")
        if runtime_s <= 0:
            raise ValueError("runtime must be > 0")
        if rfm_freq_min_s < 0:
            raise ValueError("RFM frequency min must be >= 0")
        if rfm_freq_max_s < 0:
            raise ValueError("RFM frequency max must be >= 0")
        if rfm_freq_min_s > 0 and rfm_freq_max_s > 0 and rfm_freq_max_s < rfm_freq_min_s:
            raise ValueError("RFM frequency max must be >= RFM frequency min")
        if rfm_freq_min_s > 0 and rfm_freq_max_s > 0 and rfm_freq_max_s >= 2 * rfm_freq_min_s:
            raise ValueError("RFM frequency max must be < 2 × RFM frequency min")
        if trfcrfm_s < 0:
            raise ValueError("tRFC RFM time must be >= 0")
        if tfaw_s <= 0:
            raise ValueError("tFAW must be > 0")
        if isoc < 0:
            raise ValueError("isoc must be >= 0")
        if randreset < 0:
            raise ValueError("randreset must be >= 0")
        if randreset > threshold:
            raise ValueError("randreset must be <= threshold")
        if abo_delay < 0 or abo_delay > 3:
            raise ValueError("abo_delay must be between 0 and 3")

        # Parameters
        self.rows = rows
        self.trc_s = trc_s
        self.threshold = threshold
        self.rfmabo = rfmabo
        self.abo_delay = abo_delay
        self.alert_duration_s = rfmabo * trfcrfm_s  # Calculate alert duration
        self.runtime_s = runtime_s
        self.rfm_freq_min_s = rfm_freq_min_s
        self.rfm_freq_max_s = rfm_freq_max_s
        self.trfcrfm_s = trfcrfm_s
        self.tfaw_s = tfaw_s
        self.isoc = isoc
        self.randreset = randreset

        # Workload configuration
        self.wkld = wkld
        self.feint_pct = 0
        if wkld.startswith("mixed:"):
            self.feint_pct = int(wkld.split(":")[1])
        self.rand_row_count = 131072  # 128K rows for random accesses
        
        # Store original string arguments for CSV output
        self.trc_str = trc_str
        self.rfmfreqmin_str = rfmfreqmin_str
        self.rfmfreqmax_str = rfmfreqmax_str
        self.trfcrfm_str = trfcrfm_str
        self.tfaw_str = tfaw_str
        self.runtime_str = runtime_str

        # State
        self.time_s: float = 0.0
        self.row_index: int = 0
        self.counters: List[int] = [0] * rows  # Threshold checking counters (reset on alert)
        self.total_activations_per_row: List[int] = [0] * rows  # Total activations per row (never reset)
        self.alerts_issued: List[int] = [0] * rows
        self.total_alert_time_s: List[float] = [0.0] * rows
        self.total_activations: int = 0
        self.alert_timestamps: List[float] = []  # Global list of all ALERT timestamps
        
        # tFAW constraint tracking - rolling window of last 4 activate timestamps
        self.activate_timestamps: List[float] = []  # Track activate timestamps for tFAW constraint
        
        # RFM state - windowed approach
        self.rfm_enabled = rfm_freq_min_s > 0 and rfm_freq_max_s > 0
        if self.rfm_enabled:
            self.next_rfm_window_start_s: float = rfm_freq_min_s
            self.next_rfm_window_end_s: float = rfm_freq_max_s
            self._schedule_next_rfm_in_window()  # Schedule first RFM within the first window
        else:
            self.next_rfm_window_start_s: float = float('inf')
            self.next_rfm_window_end_s: float = float('inf')
            self.next_rfm_time_s: float = float('inf')
        self.rfm_issued: List[int] = [0] * rows  # Track RFMs issued per row
        self.total_rfms: int = 0
        self.total_proactive_rfms: int = 0
        self.total_abo_rfms: int = 0
        self.total_rfm_time_s: float = 0.0

        # Active rows tracking - rows are dropped permanently after RFM in feinting/mixed modes
        self.active_rows: set = set(range(rows))

    def _schedule_next_rfm_in_window(self):
        """Schedule the next RFM at a random time within the current window."""
        if self.rfm_enabled:
            window_duration = self.next_rfm_window_end_s - self.next_rfm_window_start_s
            if window_duration > 0:
                # Random time within the window
                random_offset = random.uniform(0, window_duration)
                self.next_rfm_time_s = self.next_rfm_window_start_s + random_offset
            else:
                # No window duration, schedule at window start
                self.next_rfm_time_s = self.next_rfm_window_start_s
        else:
            self.next_rfm_time_s = float('inf')

    def run(self):
        """
        Run the simulation until the runtime elapses.
        Step:
          - If there's enough time for an ACTIVATE (tRC), perform it.
          - If it triggers an ALERT, consume alert duration immediately (GLOBAL STALL).
        """
        while True:gi
            # Check if all tracked rows have been dropped (feinting/mixed modes)
            if self.wkld != "rr" and not self.active_rows:
                break

            # Check if it's time for RFM before next activation
            if self.time_s >= self.next_rfm_time_s and self.rfm_enabled:
                # Issue RFM if we're within the window
                if self.time_s <= self.next_rfm_window_end_s:
                    self._issue_rfm()
                    # Disable further RFMs in this window by setting next_rfm_time_s beyond window end
                    self.next_rfm_time_s = float('inf')
            
            # Check if current window has expired and schedule next window
            if self.time_s >= self.next_rfm_window_end_s and self.rfm_enabled:
                # Move to next window - start at regular rfmfreqmin intervals
                self.next_rfm_window_start_s += self.rfm_freq_min_s
                self.next_rfm_window_end_s = self.next_rfm_window_start_s + (self.rfm_freq_max_s - self.rfm_freq_min_s)
                self._schedule_next_rfm_in_window()

            # Check again after RFM - all rows may have been dropped
            if self.wkld != "rr" and not self.active_rows:
                break
                
            # Can we start an ACTIVATE within the runtime?
            if self.time_s + self.trc_s > self.runtime_s:
                break

            # Check tFAW constraint before issuing ACTIVATE
            self._enforce_tfaw_constraint()
            
            # Can we still start an ACTIVATE within the runtime after tFAW delay?
            if self.time_s + self.trc_s > self.runtime_s:
                break

            # Select row based on workload type
            if self.wkld == "rr":
                # Round-robin: ACTIVATE current row
                row = self.row_index
            elif self.wkld == "feinting":
                # Feinting: find next active row
                row = self._next_active_row()
                if row is None:
                    break
            else:
                # Mixed: probabilistic choice between feinting and random
                if random.randint(1, 100) <= self.feint_pct:
                    # Feinting activation
                    row = self._next_active_row()
                    if row is None:
                        break
                else:
                    # Random access across 128K rows
                    rand_row = random.randint(0, self.rand_row_count - 1)
                    if rand_row < self.rows and rand_row in self.active_rows:
                        # Random access hit a tracked feinting row
                        row = rand_row
                    else:
                        # Random access to untracked row - just consume time
                        self.total_activations += 1
                        self.activate_timestamps.append(self.time_s)
                        if len(self.activate_timestamps) > 4:
                            self.activate_timestamps.pop(0)
                        self.time_s += self.trc_s
                        self.row_index = (self.row_index + 1) % self.rows
                        continue

            self.counters[row] += 1  # Threshold checking counter
            self.total_activations_per_row[row] += 1  # Total activations counter
            self.total_activations += 1
            
            # Record activate timestamp for tFAW tracking
            self.activate_timestamps.append(self.time_s)
            # Keep only last 4 timestamps for rolling window
            if len(self.activate_timestamps) > 4:
                self.activate_timestamps.pop(0)
            
            self.time_s += self.trc_s  # activation time consumed

            # Check threshold and possibly raise ALERT (GLOBAL STALL)
            if self.counters[row] > self.threshold and self.alert_duration_s > 0.0:
                # Issue ISOC activates first, then ALERT with RFMs
                self._handle_isoc_and_alert(row)

            # Next row (round robin)
            self.row_index = (self.row_index + 1) % self.rows

    def _next_active_row(self):
        """Find the next active row starting from row_index. Returns None if no active rows."""
        if not self.active_rows:
            return None
        for _ in range(self.rows):
            if self.row_index in self.active_rows:
                return self.row_index
            self.row_index = (self.row_index + 1) % self.rows
        return None

    def _handle_isoc_and_alert(self, triggering_row: int):
        """Issue ISOC activates first (consuming tRC each), then ALERT with reactive RFMs, with potential re-alerting."""
        isoc_activated_rows = []  # Track rows activated by ISOC
        
        # Issue ISOC activates BEFORE the ALERT (each consumes tRC)
        for _ in range(self.isoc):
            # Check if we have enough time for another activate
            if self.time_s + self.trc_s > self.runtime_s:
                break
            
            # Move to next row
            self.row_index = (self.row_index + 1) % self.rows
            if self.wkld != "rr":
                row = self._next_active_row()
                if row is None:
                    break
            else:
                row = self.row_index
            
            # ACTIVATE current row (consumes tRC)
            self.counters[row] += 1
            self.total_activations_per_row[row] += 1
            self.total_activations += 1
            # Record activate timestamp for tFAW tracking
            self.activate_timestamps.append(self.time_s)
            # Keep only last 4 timestamps for rolling window
            if len(self.activate_timestamps) > 4:
                self.activate_timestamps.pop(0)
            self.time_s += self.trc_s
            
            isoc_activated_rows.append(row)
        
        # ALERT fires: consume alert duration (GLOBAL STALL) and issue RFMs
        remaining = self.runtime_s - self.time_s
        if remaining > 0.0:
            self.alert_timestamps.append(self.time_s)  # Record when ALERT started
            consume = min(self.alert_duration_s, remaining)
            self.alerts_issued[triggering_row] += 1
            self.total_alert_time_s[triggering_row] += consume
            self.time_s += consume
        
        # Issue rfmabo number of RFMs targeting highest counter rows
        self._issue_alert_rfms()
        
        # Issue abo_delay ACTIVATEs after ALERT+RFMs (mandatory delay before next ALERT)
        for _ in range(self.abo_delay):
            if self.time_s + self.trc_s > self.runtime_s:
                break
            self.row_index = (self.row_index + 1) % self.rows
            if self.wkld != "rr":
                row = self._next_active_row()
                if row is None:
                    break
            else:
                row = self.row_index
            self.counters[row] += 1
            self.total_activations_per_row[row] += 1
            self.total_activations += 1
            # Record activate timestamp for tFAW tracking
            self.activate_timestamps.append(self.time_s)
            # Keep only last 4 timestamps for rolling window
            if len(self.activate_timestamps) > 4:
                self.activate_timestamps.pop(0)
            self.time_s += self.trc_s
            isoc_activated_rows.append(row)

        # Check which ISOC-activated rows still exceed threshold after RFMs
        re_alert_rows = [r for r in isoc_activated_rows if self.counters[r] > self.threshold]
        
        # Fire re-alerts for rows still above threshold
        for re_alert_row in re_alert_rows:
            if self.alert_duration_s > 0.0:
                self._handle_isoc_and_alert(re_alert_row)
    
    def _issue_alert_rfms(self):
        """Issue rfmabo number of RFMs targeting rows with highest counters during alert."""
        if self.wkld != "rr":
            # Feinting/mixed: operate on active rows only
            if not self.active_rows:
                return
            active_row_counters = [(self.counters[r], r) for r in self.active_rows]
            active_row_counters.sort(reverse=True, key=lambda x: x[0])
            for i in range(self.rfmabo):
                if not active_row_counters:
                    break
                target_row = active_row_counters[i % len(active_row_counters)][1]
                self.counters[target_row] = random.randint(0, self.randreset)
                self.rfm_issued[target_row] += 1
                self.total_rfms += 1
                self.total_abo_rfms += 1
                self.active_rows.discard(target_row)
        else:
            # Round-robin: operate on all rows
            all_rows = [(self.counters[r], r) for r in range(self.rows)]
            all_rows.sort(reverse=True, key=lambda x: x[0])
            for i in range(self.rfmabo):
                target_row = all_rows[i % len(all_rows)][1]
                self.counters[target_row] = random.randint(0, self.randreset)
                self.rfm_issued[target_row] += 1
                self.total_rfms += 1
                self.total_abo_rfms += 1
            
    def _issue_rfm(self):
        """Issue RFM to the row closest to exceeding threshold."""
        if self.wkld != "rr":
            # Feinting/mixed: operate on active rows only
            if not self.active_rows:
                return
            max_counter = -1
            target_row = None
            for r in self.active_rows:
                if self.counters[r] > max_counter:
                    max_counter = self.counters[r]
                    target_row = r
            if target_row is not None and max_counter > 0:
                self.counters[target_row] = random.randint(0, self.randreset)
                self.rfm_issued[target_row] += 1
                self.total_rfms += 1
                self.total_proactive_rfms += 1
                self.active_rows.discard(target_row)
                if self.trfcrfm_s > 0:
                    remaining = self.runtime_s - self.time_s
                    if remaining > 0:
                        consume = min(self.trfcrfm_s, remaining)
                        self.total_rfm_time_s += consume
                        self.time_s += consume
        else:
            # Round-robin: operate on all rows
            max_counter = max(self.counters)
            if max_counter > 0:
                target_row = self.counters.index(max_counter)
                self.counters[target_row] = random.randint(0, self.randreset)
                self.rfm_issued[target_row] += 1
                self.total_rfms += 1
                self.total_proactive_rfms += 1
                if self.trfcrfm_s > 0:
                    remaining = self.runtime_s - self.time_s
                    if remaining > 0:
                        consume = min(self.trfcrfm_s, remaining)
                        self.total_rfm_time_s += consume
                        self.time_s += consume
        
        # Note: Next RFM is scheduled in the run loop when window expires
        
    def _enforce_tfaw_constraint(self):
        """Enforce tFAW constraint: maximum 4 activates in any tFAW window.
        
        If we already have 4 activates in the last tFAW interval,
        advance time until the oldest activate is outside the window.
        """
        # Remove old timestamps outside the tFAW window
        current_time = self.time_s
        self.activate_timestamps = [t for t in self.activate_timestamps if current_time - t < self.tfaw_s]
        
        # If we have 4 activates in the current tFAW window, we must wait
        if len(self.activate_timestamps) >= 4:
            # Find the oldest activate timestamp
            oldest_activate = self.activate_timestamps[0]
            # Calculate when that activate will be outside the tFAW window
            earliest_next_activate = oldest_activate + self.tfaw_s
            
            # If we need to wait, advance time
            if current_time < earliest_next_activate:
                self.time_s = earliest_next_activate
                # Clean up the activate timestamps list again after time advancement
                self.activate_timestamps = [t for t in self.activate_timestamps if self.time_s - t < self.tfaw_s]

    def summary(self) -> str:
        """Build a human-readable summary of the simulation results."""
        used_time = self.time_s
        idle_time = max(0.0, self.runtime_s - used_time)
        total_alert = sum(self.total_alert_time_s)

        lines = []
        lines.append("=== DRAM Activation Simulation Summary ===")
        lines.append(f"Runtime:            {human_time(self.runtime_s)}")
        lines.append(f"tRC per activate:   {human_time(self.trc_s)}")
        lines.append(f"tFAW:               {human_time(self.tfaw_s)}")
        lines.append(f"Rows:               {self.rows}")
        lines.append(f"Threshold (>):      {self.threshold}")
        lines.append(f"tRFC per RFM:       {human_time(self.trfcrfm_s)}")
        lines.append(f"RFM ABO:            {self.rfmabo}")
        lines.append(f"ISOC:               {self.isoc}")
        lines.append(f"ABO Delay:          {self.abo_delay}")
        lines.append(f"RandReset:          {self.randreset}")
        lines.append(f"Workload:           {self.wkld}")
        if self.trfcrfm_s > 0:
            lines.append(f"ALERT servicing duration: {human_time(self.alert_duration_s)} (RFM ABO × tRFC per RFM)")
        else:
            lines.append(f"ALERT servicing duration: {human_time(self.alert_duration_s)}")
        lines.append("")
        lines.append(f"Total ACTIVATEs:    {self.total_activations}")
        lines.append(f"Used time:          {human_time(used_time)}")
        lines.append(f"Idle time:          {human_time(idle_time)}")
        lines.append("")
        lines.append(f"Total RFMs:         {self.total_rfms}")
        lines.append(f"ABO-based RFMs:     {self.total_abo_rfms}")
        lines.append(f"Proactive RFMs:     {self.total_proactive_rfms}")
        if self.rfm_enabled:
            window_duration = self.rfm_freq_max_s - self.rfm_freq_min_s
            lines.append(f"RFM window start:   {human_time(self.rfm_freq_min_s)}")
            lines.append(f"RFM window end:     {human_time(self.rfm_freq_max_s)}")
            lines.append(f"RFM window dur.:    {human_time(window_duration)}")
        lines.append(f"Proactive RFM time: {human_time(self.total_rfm_time_s)}")

        # ALERT statistics
        if len(self.alert_timestamps) >= 2:
            gaps = [self.alert_timestamps[i+1] - self.alert_timestamps[i] - self.alert_duration_s
                   for i in range(len(self.alert_timestamps) - 1)]
            # Two ALERTs are consecutive when separated by exactly (isoc + abo_delay) activations
            consec_gap = (self.isoc + self.abo_delay) * self.trc_s
            longest_consec_count = 1
            current_consec_count = 1
            for g in gaps:
                if is_float_zero(g - consec_gap):
                    current_consec_count += 1
                    longest_consec_count = max(longest_consec_count, current_consec_count)
                else:
                    current_consec_count = 1  # Reset sequence

            lines.append("")
            lines.append(f"Total ALERTs:       {len(self.alert_timestamps)}")
            lines.append(f"Total ALERT servicing time: {human_time(total_alert)}")
            lines.append(f"Longest seq. consecutive ALERTs: {longest_consec_count}")
        elif len(self.alert_timestamps) == 1:
            lines.append("")
            lines.append(f"Total ALERTs:       1")
            lines.append(f"Total ALERT servicing time: {human_time(total_alert)}")

        # Per-row metrics
        lines.append("")
        lines.append("Per-row metrics:")
        # Always show RFMs column since RFMs can be issued both proactively and in response to ALERTs
        lines.append(f"{'Row':>6} | {'ACTIVATEs':>12} | {'ALERTs':>6} | {'RFMs':>6} | {'ALERT Time':>12}")
        lines.append("-" * 58)
        for r in range(self.rows):
            lines.append(
                f"{r:6d} | {self.total_activations_per_row[r]:12d} | {self.alerts_issued[r]:6d} | {self.rfm_issued[r]:6d} | {human_time(self.total_alert_time_s[r]):>12}"
            )
        return "\n".join(lines)

    def _compute_alert_metrics(self):
        """Compute ALERT metrics from timestamps."""
        total_alerts = len(self.alert_timestamps)
        if total_alerts >= 2:
            gaps = [self.alert_timestamps[i+1] - self.alert_timestamps[i] - self.alert_duration_s
                   for i in range(len(self.alert_timestamps) - 1)]
            # Two ALERTs are consecutive when separated by exactly (isoc + abo_delay) activations
            consec_gap = (self.isoc + self.abo_delay) * self.trc_s
            longest_consec_count = 1
            current_consec_count = 1
            for g in gaps:
                if is_float_zero(g - consec_gap):
                    current_consec_count += 1
                    longest_consec_count = max(longest_consec_count, current_consec_count)
                else:
                    current_consec_count = 1
            return total_alerts, longest_consec_count
        else:
            return total_alerts, total_alerts

    def csv_output(self) -> str:
        """Output metrics in CSV format: rows,trc,tfaw,threshold,isoc,abo_delay,rfmabo,rfmfreqmin,rfmfreqmax,trfcrfm,runtime,Row,ACTIVATEs,ALERTs,RFMs,ALERTTime,TotalALERTs,LongestSeqConsecALERTs"""
        # Input parameters first
        input_params = f"{self.rows},{self.trc_str},{self.tfaw_str},{self.threshold},{self.isoc},{self.abo_delay},{self.rfmabo},{self.rfmfreqmin_str},{self.rfmfreqmax_str},{self.trfcrfm_str},{self.runtime_str}"
        
        # ALERT metrics
        total_alerts, longest_consec = self._compute_alert_metrics()
        alert_metrics = f"{total_alerts},{longest_consec}"
        
        if self.rows == 1:
            # Single row - always include RFMs count (both proactive and alert RFMs)
            metrics = f"0,{self.total_activations_per_row[0]},{self.alerts_issued[0]},{self.rfm_issued[0]},{self.total_alert_time_s[0]}"
        else:
            # Multiple rows - output summed totals with "ALL" as row identifier
            total_activations = sum(self.total_activations_per_row)
            total_alerts_issued = sum(self.alerts_issued)
            total_alert_time = sum(self.total_alert_time_s)
            total_rfms = sum(self.rfm_issued)  # Always include total RFMs
            metrics = f"ALL,{total_activations},{total_alerts_issued},{total_rfms},{total_alert_time}"
        
        return f"{input_params},{metrics},{alert_metrics}"


def main(argv=None):
    params = parse_and_validate_args(argv)
    if isinstance(params, int):
        return params

    csv = params.pop("csv")
    seed = params.pop("seed")
    random.seed(seed)
    sim = DRAMSimulator(**params)
    sim.run()
    if csv:
        print(sim.csv_output())
    else:
        print(sim.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
