
# DRAMSimVS — Visual Studio Code Python Project

This is a ready-to-use **Visual Studio Code** project for the DRAM activation simulator with windowed RFM (Row Fresh Management) functionality.

## Features

- **Windowed RFM**: Configurable proactive RFM with randomized timing windows
- **Alert-based RFM**: Reactive RFMs triggered by threshold violations
- **Comprehensive metrics**: Tracks activations, alerts, RFMs, and timing
- **CSV output**: Parameter sweep-friendly output format
- **Flexible timing**: Support for ns, us, ms, s time units

## Files

- `dram_sim.py` — The DRAM activation simulator
- `DRAMSimVS.code-workspace` — VS Code workspace file
- `.vscode/` — VS Code configuration (settings, launch configs, tasks)
- `requirements.txt` — Python dependencies (currently none)
- `.venv/` — Python virtual environment

## Setup

### Prerequisites
- **Visual Studio Code** with Python extension
- **Python 3.7+**

### Quick Start
1. Open VS Code
2. `File` → `Open Workspace from File`
3. Select `DRAMSimVS.code-workspace`
4. VS Code will automatically:
   - Use the `.venv` virtual environment
   - Configure Python interpreter
   - Load debug/run configurations

## Usage

### Running the Simulator

**At Terminal**
```bash
python dram_sim.py --rows 8 --trc 45ns --threshold 1000 --rfmabo 2 --trfcrfm 200ns --runtime 10ms
```

### Command Line Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--rows` | Number of rows to simulate | `4` |
| `--trc` | tRC time per ACTIVATE | `45ns` |
| `--threshold` | Alert threshold (counter >) | `16000` |
| `--rfmabo` | RFMs issued per alert | `64` |
| `--trfcrfm` | tRFC RFM time duration | `350ns` |
| `--rfmfreqmin` | RFM window start time | `32us` |
| `--rfmfreqmax` | RFM window end time | `48us` |
| `--runtime` | Total simulation time | `64ms` |
| `--csv` | CSV output format | (flag) |

### Example Commands

**Basic simulation:**
```bash
python dram_sim.py --rows 4 --trc 45ns --threshold 1000 --rfmabo 1 --trfcrfm 400ns --runtime 10ms
```

**With windowed RFM:**
```bash
python dram_sim.py --rows 8 --trc 45ns --threshold 2000 --rfmabo 2 --trfcrfm 200ns --rfmfreqmin 24us --rfmfreqmax 36us --runtime 64ms
```

**CSV output for parameter sweeps:**
```bash
python dram_sim.py --rows 1 --trc 45ns --threshold 500 --rfmabo 4 --trfcrfm 100ns --runtime 10ms --csv
```

## Output Formats

### Standard Output
```
=== DRAM Activation Simulation Summary ===
Runtime:            10.000 ms
Total ACTIVATEs:    218364
Total RFMs issued:  2659
Per-row metrics:
   Row |  Activations | Alerts |   RFMs |   Alert Time
   ...
```

### CSV Output
```
rows,trc,threshold,rfmabo,rfmfreqmin,rfmfreqmax,trfcrfm,runtime,Row,Activations,Alerts,RFMs,AlertTime
8,45ns,1000,2,24us,36us,200ns,10ms,ALL,171651,0,6502,0.0
```

## Development

### Extending the Project
1. Modify `dram_sim.py` for new features
2. Update launch configurations in `.vscode/launch.json`
3. Add new tasks in `.vscode/tasks.json`
4. Install dependencies: `pip install <package>` then update `requirements.txt`

## Notes

- **Time Units**: Supports ns (nanoseconds), us (microseconds), ms (milliseconds), s (seconds)
- **RFM Types**: Both proactive (windowed) and reactive (alert-based) RFMs are counted
- **CSV Format**: Designed for easy parameter sweep analysis and data processing
