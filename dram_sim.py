#!/usr/bin/env python3
"""
PRAC Denial of Service simulator for DRAM ACTIVATEs with GLOBAL ALERT stalls.

Supports two modes:
- report:  Uses DRAM timings specific to the selected DRAM type (e.g., 'ddr5').
- explore: DRAM timings are passed via command-line flags.

Behavior:
- Round-robin ACTIVATEs across N rows.
- Each ACTIVATE consumes tRC time.
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

Inputs (report mode):
- --dram-type      DRAM type (e.g., 'ddr5') for loading protocol parameters from config.

Inputs (explore mode):
- --trc            tRC per ACTIVATE (e.g., '45ns', '3.2us', '64ms', '0.001s').
- --rfmabo         Number of RFMs issued in response to ABO.
- --trfcrfm        tRFC RFM time duration consumed when RFM is issued (e.g., '100ns', '1us'). Use '0' for no time consumption.
- --isoc           Number of activates issued after alert but before reactive RFMs (default 0).
- --randreset      Range for random counter reset (0 to randreset). Default is 0 (always reset to 0).
- --runtime        Total simulation runtime (default 128 ms).

Notes:
- ALERT time is a GLOBAL STALL: while an alert is active, no activates occur.
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
        runtime_s: float = 0.128,
        rfm_freq_min_s: float = 0.0,
        rfm_freq_max_s: float = 0.0,
        trfcrfm_s: float = 0.0,
        isoc: int = 0,
        randreset: int = 0,
        # Original string arguments for CSV output
        trc_str: str = "",
        rfmfreqmin_str: str = "",
        rfmfreqmax_str: str = "",
        trfcrfm_str: str = "",
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
        if isoc < 0:
            raise ValueError("isoc must be >= 0")
        if randreset < 0:
            raise ValueError("randreset must be >= 0")

        # Parameters
        self.rows = rows
        self.trc_s = trc_s
        self.threshold = threshold
        self.rfmabo = rfmabo
        self.alert_duration_s = rfmabo * trfcrfm_s  # Calculate alert duration
        self.runtime_s = runtime_s
        self.rfm_freq_min_s = rfm_freq_min_s
        self.rfm_freq_max_s = rfm_freq_max_s
        self.trfcrfm_s = trfcrfm_s
        self.isoc = isoc
        self.randreset = randreset
        
        # Store original string arguments for CSV output
        self.trc_str = trc_str
        self.rfmfreqmin_str = rfmfreqmin_str
        self.rfmfreqmax_str = rfmfreqmax_str
        self.trfcrfm_str = trfcrfm_str
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
        while True:
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
                
            # Can we start an ACTIVATE within the runtime?
            if self.time_s + self.trc_s > self.runtime_s:
                break

            # ACTIVATE current row
            row = self.row_index
            self.counters[row] += 1  # Threshold checking counter
            self.total_activations_per_row[row] += 1  # Total activations counter
            self.total_activations += 1
            self.time_s += self.trc_s  # activation time consumed

            # Check threshold and possibly raise ALERT (GLOBAL STALL)
            if self.counters[row] > self.threshold and self.alert_duration_s > 0.0:
                # Issue ISOC activates first, then ALERT with RFMs
                self._handle_isoc_and_alert(row)

            # Next row (round robin)
            self.row_index = (self.row_index + 1) % self.rows

    def _handle_isoc_and_alert(self, triggering_row: int):
        """Issue ISOC activates first (consuming tRC each), then ALERT with reactive RFMs, with potential re-alerting."""
        isoc_activated_rows = []  # Track rows activated by ISOC
        
        # Issue ISOC activates BEFORE the ALERT (each consumes tRC)
        for _ in range(self.isoc):
            # Check if we have enough time for another activate
            if self.time_s + self.trc_s > self.runtime_s:
                break
            
            # Move to next row (round robin continues)
            self.row_index = (self.row_index + 1) % self.rows
            row = self.row_index
            
            # ACTIVATE current row (consumes tRC)
            self.counters[row] += 1
            self.total_activations_per_row[row] += 1
            self.total_activations += 1
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
        
        # Check which ISOC-activated rows still exceed threshold after RFMs
        re_alert_rows = [r for r in isoc_activated_rows if self.counters[r] > self.threshold]
        
        # Fire re-alerts for rows still above threshold
        for re_alert_row in re_alert_rows:
            if self.alert_duration_s > 0.0:
                self._handle_isoc_and_alert(re_alert_row)
    
    def _issue_alert_rfms(self):
        """Issue rfmabo number of RFMs targeting rows with highest counters during alert."""
        # Get list of (counter_value, row_index) pairs for ALL rows, sorted by counter value (highest first)
        all_rows = [(self.counters[r], r) for r in range(self.rows)]
        all_rows.sort(reverse=True, key=lambda x: x[0])
        
        # Always issue exactly rfmabo RFMs, regardless of counter values
        for i in range(self.rfmabo):
            # Target rows in order of highest counters first, cycling through all rows if needed
            target_row = all_rows[i % len(all_rows)][1]
            # Reset counter to random value between 0 and randreset
            self.counters[target_row] = random.randint(0, self.randreset)
            self.rfm_issued[target_row] += 1
            self.total_rfms += 1
            self.total_abo_rfms += 1
            
    def _issue_rfm(self):
        """Issue RFM to the row closest to exceeding threshold."""
        # Find row with highest counter value (closest to threshold)
        max_counter = max(self.counters)
        if max_counter > 0:  # Only issue RFM if there are activations to reset
            # Find the first row with the maximum counter value
            target_row = self.counters.index(max_counter)
            # Reset counter to random value between 0 and randreset
            self.counters[target_row] = random.randint(0, self.randreset)
            self.rfm_issued[target_row] += 1
            self.total_rfms += 1
            self.total_proactive_rfms += 1
            
            # Consume RFM time if specified and runtime allows
            if self.trfcrfm_s > 0:
                remaining = self.runtime_s - self.time_s
                if remaining > 0:
                    consume = min(self.trfcrfm_s, remaining)
                    self.total_rfm_time_s += consume
                    self.time_s += consume
        
        # Note: Next RFM is scheduled in the run loop when window expires

    def summary(self) -> str:
        """Build a human-readable summary of the simulation results."""
        used_time = self.time_s
        idle_time = max(0.0, self.runtime_s - used_time)
        total_alert = sum(self.total_alert_time_s)

        lines = []
        lines.append("=== DRAM Activation Simulation Summary ===")
        lines.append(f"Runtime:            {human_time(self.runtime_s)}")
        lines.append(f"tRC per activate:   {human_time(self.trc_s)}")
        lines.append(f"Rows:               {self.rows}")
        lines.append(f"Threshold (>):      {self.threshold}")
        lines.append(f"tRFC per RFM:       {human_time(self.trfcrfm_s)}")
        lines.append(f"RFM ABO:            {self.rfmabo}")
        lines.append(f"ISOC:               {self.isoc}")
        lines.append(f"RandReset:          {self.randreset}")
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
            # Two ALERTs are back-to-back when separated by exactly isoc activations
            b2b_gap = self.isoc * self.trc_s

            # Longest consecutive back-to-back sequence (counted by ALERTs)
            longest_b2b_count = 1
            current_b2b_count = 1
            for g in gaps:
                if is_float_zero(g - b2b_gap):
                    current_b2b_count += 1
                    longest_b2b_count = max(longest_b2b_count, current_b2b_count)
                else:
                    current_b2b_count = 1  # Reset sequence

            lines.append("")
            lines.append(f"Total ALERTs:       {len(self.alert_timestamps)}")
            lines.append(f"Total ALERT servicing time: {human_time(total_alert)}")
            lines.append(f"Longest seq. back-to-back ALERTs: {longest_b2b_count}")
        elif len(self.alert_timestamps) == 1:
            lines.append("")
            lines.append(f"Total ALERTs:       1")
            lines.append(f"Total ALERT servicing time: {human_time(total_alert)}")

        # Per-row metrics
        lines.append("")
        lines.append("Per-row metrics:")
        # Always show RFMs column since RFMs can be issued both proactively and in response to ALERTs
        lines.append(f"{'Row':>6} | {'Activations':>12} | {'ALERTs':>6} | {'RFMs':>6} | {'ALERT Time':>12}")
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
            # Two ALERTs are back-to-back when separated by exactly isoc activations
            b2b_gap = self.isoc * self.trc_s
            longest_b2b_count = 1
            current_b2b_count = 1
            for g in gaps:
                if is_float_zero(g - b2b_gap):
                    current_b2b_count += 1
                    longest_b2b_count = max(longest_b2b_count, current_b2b_count)
                else:
                    current_b2b_count = 1
            return total_alerts, longest_b2b_count
        else:
            return total_alerts, 1

    def csv_output(self) -> str:
        """Output metrics in CSV format: rows,trc,threshold,isoc,rfmabo,rfmfreqmin,rfmfreqmax,trfcrfm,runtime,Row,Activations,ALERTs,RFMs,ALERTTime,TotalALERTs,LongestSeqB2BALERTs"""
        # Input parameters first
        input_params = f"{self.rows},{self.trc_str},{self.threshold},{self.isoc},{self.rfmabo},{self.rfmfreqmin_str},{self.rfmfreqmax_str},{self.trfcrfm_str},{self.runtime_str}"
        
        # ALERT metrics
        total_alerts, longest_b2b = self._compute_alert_metrics()
        alert_metrics = f"{total_alerts},{longest_b2b}"
        
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
    sim = DRAMSimulator(**params)
    sim.run()
    if csv:
        print(sim.csv_output())
    else:
        print(sim.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
