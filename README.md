
# PRAC Denial of Service Simulator

This is a ready-to-use **Visual Studio Code** project for the PRAC (Per Row Activation Counting) Denial of Service simulator for DRAM ACTIVATEs with GLOBAL ALERT stalls.

## Features

- **Two simulation modes**:
  - `report`: Uses DRAM timings specific to the selected DRAM type (e.g., 'ddr5')
  - `explore`: DRAM timings are passed via command-line flags
- **Round-robin ACTIVATEs**: Activations cycle across N rows
- **GLOBAL ALERT stalls**: When a counter exceeds threshold, ALERT duration is consumed immediately (no ACTIVATEs to ANY row during ALERT)
- **Windowed RFM**: Configurable proactive RFM with randomized timing windows
  For example if rfmfreqmin = 32us & rfmfreqmax = 48us then every 32us a 16us window starts where a random RFM will be issued
  ```
  Time:     0us   32us   48us   64us   80us   96us   112us
  Windows:        [----W1---]   [----W2---]   [-----W3---]
  RFM:             ↑random       ↑random       ↑random
  ```
- **Alert-based RFM**: Reactive RFMs triggered by threshold violations
- **Comprehensive metrics**: Tracks activations, alerts, RFMs, and per-row alert time
- **CSV output**: Parameter sweep-friendly output format
- **Flexible timing**: Support for ns, us (or µs), ms, s time units

## Setup

### Prerequisites
- **Python 3.7+**

### Quick Start
1. Install dependencies: `pip install -r requirements.txt`
2. Run the simulator (see Usage below)

## Usage

### Running the Simulator

The simulator supports two modes: `report` and `explore`.

**Report mode** (uses DRAM config file):
```bash
python dram_sim.py report --dram-type ddr5 --rows 8 --threshold 1000
```

**Explore mode** (all parameters via command line):
```bash
python dram_sim.py explore --rows 8 --trc 45ns --threshold 1000 --rfmabo 2 --trfcrfm 410ns --runtime 32ms
```

### Command Line Parameters

#### Common Parameters (both modes)

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--rows` | Number of rows to operate on | `8` |
| `--threshold` | Counter threshold; ALERT raised when counter > threshold | `1000` |
| `--rfmfreqmin` | RFM window start time (use '0' to disable RFM) | `32us` |
| `--rfmfreqmax` | RFM window end time (must be >= rfmfreqmin, use '0' to disable RFM) | `48us` |
| `--randreset`  | range of random values that row counter is reset to after serviced by RFM | `0` |
| `--csv` | CSV output format | (flag) |

#### Report Mode Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--dram-type` | DRAM type for loading protocol parameters from config | `ddr5` |

#### Explore Mode Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--trc` | tRC per ACTIVATE (e.g., '45ns', '3us', '64ms', '0.001s') | `45ns` |
| `--isoc` | Number of ACTIVATEs issued between ALERT and re-active RFM | `0` |
| `--rfmabo` | RFM ABO multiplier; alert duration = rfmabo × trfcrfm | `4` |
| `--abo_delay` | Minimum number of ACTIVATEs between two consecutive ALERTs (0 to 3) | `0` |
| `--trfcrfm` | tRFC RFM time duration consumed when RFM is issued (use '0' for no time consumption) | `410ns` |
| `--runtime` | Total simulation runtime | `32ms` |

### Example Commands

**Report mode with DDR5 config:**
```bash
python dram_sim.py report --dram-type ddr5 --rows 4 --threshold 1000
```

**Report mode with windowed RFM:**
```bash
python dram_sim.py report --dram-type ddr5 --rows 8 --threshold 2000 --rfmfreqmin 24us --rfmfreqmax 36us
```

**Explore mode basic simulation:**
```bash
python dram_sim.py explore --rows 4 --trc 45ns --threshold 1000 --rfmabo 1 --trfcrfm 410ns --runtime 32ms
```

**Explore mode with windowed RFM:**
```bash
python dram_sim.py explore --rows 8 --trc 45ns --threshold 2000 --rfmabo 2 --trfcrfm 410ns --rfmfreqmin 24us --rfmfreqmax 36us --runtime 32ms
```

**CSV output for parameter sweeps:**
```bash
python dram_sim.py explore --rows 1 --trc 45ns --threshold 500 --rfmabo 4 --trfcrfm 410ns --runtime 32ms --csv
```

## Output Formats

### Standard Output
```
=== DRAM Activation Simulation Summary ===
Runtime:            32.000 ms
tRC per activate:   45.000 ns
Rows:               8
Threshold (>):      1000
tRFC per RFM:       410.000 ns
RFM ABO:            4
ISOC:               0
ABO Delay:          0
RandReset:          0
ALERT servicing duration: 1.640 us (RFM ABO × tRFC per RFM)

Total ACTIVATEs:    704696
Used time:          32.000 ms
Idle time:          40.000 ns

Total RFMs:         704
ABO-based RFMs:     704
Proactive RFMs:     0
Proactive RFM time: 0.000 ns

Total ALERTs:       176
Total ALERT servicing time: 288.640 us
Longest seq. consecutive ALERTs: 1

Per-row metrics:
   Row |    ACTIVATEs | ALERTs |   RFMs |   ALERT Time
----------------------------------------------------------
     0 |        88087 |     22 |     88 |    36.080 us
     1 |        88087 |     22 |     88 |    36.080 us
     2 |        88087 |     22 |     88 |    36.080 us
     3 |        88087 |     22 |     88 |    36.080 us
     4 |        88087 |     22 |     88 |    36.080 us
     5 |        88087 |     22 |     88 |    36.080 us
     6 |        88087 |     22 |     88 |    36.080 us
     7 |        88087 |     22 |     88 |    36.080 us
```

### CSV Output
```
rows,trc,threshold,isoc,abo_delay,rfmabo,rfmfreqmin,rfmfreqmax,trfcrfm,runtime,Row,ACTIVATEs,ALERTs,RFMs,ALERTTime,TotalALERTs,LongestSeqConsecALERTs
8,45ns,1000,0,2,24us,36us,200ns,10ms,ALL,171651,0,6502,0.0,0,1
```

## Notes

- **Time Units**: Supports ns (nanoseconds), us (microseconds), ms (milliseconds), s (seconds)
- **RFM Types**: Both proactive (windowed) and reactive (alert-based) RFMs are counted
- **CSV Format**: Designed for easy parameter sweep analysis and data processing
- **Consecutive ALERTs**: Two ALERTs are considered *consecutive* when the gap between them (end of previous ALERT to start of next ALERT) equals exactly `(isoc + abo_delay) × tRC`. This accounts for the ISOC activations that occur before the ALERT and the mandatory ABO delay activations that occur after the ALERT. When both `isoc=0` and `abo_delay=0`, consecutive means zero gap (i.e., one ALERT fires immediately after the previous one ends).
