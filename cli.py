"""Command-line interface for the DRAM PRAC simulator."""

import argparse
import importlib
import sys

from utils import parse_time_to_seconds


def _build_arg_parser():
    """Build the argument parser with report and explore subcommands."""
    p = argparse.ArgumentParser(
        description="Simulate DRAM ACTIVATEs with GLOBAL ALERT stalls due to PRAC.",
        add_help=False,
    )
    p.add_argument("-h", "--help", action="store_true", help="show this help message and exit")
    subparsers = p.add_subparsers(dest="mode", title="modes", metavar="mode", help="Simulation mode (default: report)")

    # Report mode - protocol parameters from config file (default, listed first)
    report = subparsers.add_parser(
        "report",
        help="Report mode (default): DRAM protocol parameters from config file",
        add_help=False,
    )
    report.add_argument("--dram-type", type=str, required=True, dest="dram_type", help="DRAM type (e.g., 'ddr5').")
    report.add_argument("--rows", type=int, required=True, help="Number of rows to operate on.")
    report.add_argument(
        "--threshold", type=int, required=True,
        help="Counter threshold; ALERT raised when counter strictly exceeds this value."
    )
    report.add_argument(
        "--rfmfreqmin", type=str, default="0",
        help="RFM (Row Fresh Management) window start time (e.g., '32us', '64us'). Use '0' to disable RFM. Default is 0 (disabled)."
    )
    report.add_argument(
        "--rfmfreqmax", type=str, default="0",
        help="RFM (Row Fresh Management) window end time (e.g., '48us', '80us'). Must be >= rfmfreqmin and < 2×rfmfreqmin. Default is 0 (disabled)."
    )
    report.add_argument(
        "--randreset", type=int, default=0,
        help="Range for random counter reset (0 to randreset). Default is 0 (always reset to 0)."
    )
    report.add_argument(
        "--seed", type=int, default=0,
        help="Seed for random number generator. Default is 0."
    )
    report.add_argument(
        "--csv", action="store_true",
        help="Output results in CSV format: Row,ACTIVATEs,ALERTs,RFMs,ALERTTime"
    )

    # Explore mode - all flags on command line
    explore = subparsers.add_parser(
        "explore",
        help="Explore mode: all parameters via command-line flags",
        add_help=False,
    )
    explore.add_argument("--rows", type=int, required=True, help="Number of rows to operate on.")
    explore.add_argument("--trc", type=str, required=True, help="tRC per ACTIVATE (e.g., '45ns', '3us', '64ms', '0.001s').")
    explore.add_argument("--tfaw", type=str, default="20ns", help="tFAW timing constraint for 4 activates window (e.g., '20ns', '25ns'). Default is 20ns.")
    explore.add_argument(
        "--threshold", type=int, required=True,
        help="Counter threshold; ALERT raised when counter strictly exceeds this value."
    )
    explore.add_argument(
        "--rfmabo", type=int, required=True,
        help="RFM ABO multiplier; alert duration = rfmabo × trfcrfm."
    )
    explore.add_argument(
        "--isoc", type=int, default=0,
        help="Number of ACTIVATEs issued after alert but before reactive RFMs. Default is 0."
    )
    explore.add_argument(
        "--randreset", type=int, default=0,
        help="Range for random counter reset (0 to randreset). Default is 0 (always reset to 0)."
    )
    explore.add_argument(
        "--seed", type=int, default=0,
        help="Seed for random number generator. Default is 0."
    )
    explore.add_argument(
        "--abo_delay", type=int, default=0,
        help="Minimum number of ACTIVATEs between two consecutive ALERTs (0 to 3). Default is 0."
    )
    explore.add_argument("--runtime", type=str, default="128ms", help="Total simulation runtime. Default is 128ms.")
    explore.add_argument(
        "--rfmfreqmin", type=str, default="0",
        help="RFM (Row Fresh Management) window start time (e.g., '32us', '64us'). Use '0' to disable RFM. Default is 0 (disabled)."
    )
    explore.add_argument(
        "--rfmfreqmax", type=str, default="0",
        help="RFM (Row Fresh Management) window end time (e.g., '48us', '80us'). Must be >= rfmfreqmin and < 2×rfmfreqmin. Default is 0 (disabled)."
    )
    explore.add_argument(
        "--trfcrfm", type=str, default="0",
        help="tRFC RFM time duration consumed when RFM is issued (e.g., '100ns', '1us'). Use '0' for no time consumption. Default is 0."
    )
    explore.add_argument(
        "--csv", action="store_true",
        help="Output results in CSV format: Row,ACTIVATEs,ALERTs,RFMs,ALERTTime"
    )

    return p, report, explore


def _load_config(dram_type: str):
    """Load DRAM protocol parameters from Python configuration module."""
    try:
        config_module = importlib.import_module(f"{dram_type}_config")
    except ModuleNotFoundError:
        raise ModuleNotFoundError(f"Configuration module not found: {dram_type}_config")

    required_vars = ['trc', 'rfmabo', 'trfcrfm', 'refw']
    for var in required_vars:
        if not hasattr(config_module, var):
            raise ValueError(f"Configuration module missing required variable: {var}")

    return config_module


def _print_parser_help(subparser, mode_name: str, description: str):
    """Print compact help for a subparser using the same format as main help."""
    print(f"usage: {sys.argv[0]} {mode_name} [options]\n")
    print(f"{description}\n")
    print(f"{mode_name} mode flags:")
    for action in subparser._actions:
        if action.option_strings:
            opts = ", ".join(action.option_strings)
            print(f"  {opts:20} {action.help}")


def parse_and_validate_args(argv=None):
    """Parse CLI arguments, load config if needed, validate, and return sim parameters.

    Returns a dict with keys:
        rows, trc_s, threshold, rfmabo, runtime_s, rfm_freq_min_s, rfm_freq_max_s,
        trfcrfm_s, isoc, trc_str, rfmfreqmin_str, rfmfreqmax_str, trfcrfm_str,
        runtime_str, csv
    Or returns an int exit code if help was shown or an error occurred.
    """
    parser, report_parser, explore_parser = _build_arg_parser()

    # Handle custom help: show modes + report flags
    if argv is None and (len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"))):
        print(f"usage: {sys.argv[0]} [-h] mode ...\n")
        print("Simulate DRAM ACTIVATEs with GLOBAL ALERT stalls due to PRAC.\n")
        print("modes:")
        print("  mode        Simulation mode (default: report)")
        print("    report    Report mode (default): DRAM protocol parameters from config file")
        print("    explore   Explore mode: all parameters via command-line flags\n")
        print("report mode flags:")
        for action in report_parser._actions:
            if action.option_strings:
                opts = ", ".join(action.option_strings)
                print(f"  {opts:20} {action.help}")
        print(f"\nFor explore mode flags, run: {sys.argv[0]} explore --help")
        return 0

    # Handle subcommand help
    if argv is None and len(sys.argv) == 3 and sys.argv[2] in ("-h", "--help"):
        if sys.argv[1] == "report":
            _print_parser_help(report_parser, "report", "Report mode: DRAM protocol parameters from config file.")
            return 0
        elif sys.argv[1] == "explore":
            _print_parser_help(explore_parser, "explore", "Explore mode: all parameters via command-line flags.")
            return 0

    args = parser.parse_args(argv)

    # Default to report mode if no mode specified
    if args.mode is None:
        args.mode = "report"

    # Load parameters based on mode
    if args.mode == "report":
        try:
            config = _load_config(args.dram_type)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        trc_str = config.trc
        tfaw_str = getattr(config, 'tfaw', '20ns')  # Default to 20ns if not in config
        rfmabo = int(config.rfmabo)
        trfcrfm_str = config.trfcrfm
        runtime_str = config.refw
        isoc = getattr(config, 'isoc', 0)
        randreset = args.randreset
        abo_delay = getattr(config, 'abo_delay', 0)
    else:  # explore mode
        trc_str = args.trc
        tfaw_str = args.tfaw
        rfmabo = args.rfmabo
        trfcrfm_str = args.trfcrfm
        runtime_str = args.runtime
        isoc = args.isoc
        randreset = args.randreset
        abo_delay = args.abo_delay

    rfmfreqmin_str = args.rfmfreqmin
    rfmfreqmax_str = args.rfmfreqmax

    try:
        trc_s = parse_time_to_seconds(trc_str)
        tfaw_s = parse_time_to_seconds(tfaw_str)
        runtime_s = parse_time_to_seconds(runtime_str)
        rfm_freq_min_s = parse_time_to_seconds(rfmfreqmin_str)
        rfm_freq_max_s = parse_time_to_seconds(rfmfreqmax_str)
        trfcrfm_s = parse_time_to_seconds(trfcrfm_str)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Validate abo_delay range
    if abo_delay < 0 or abo_delay > 3:
        print(f"Error: abo_delay must be between 0 and 3, got {abo_delay}", file=sys.stderr)
        return 2

    # Validate RFM frequency range
    if rfm_freq_min_s > 0 and rfm_freq_max_s > 0 and rfm_freq_max_s < rfm_freq_min_s:
        print(f"Error: rfmfreqmax ({rfmfreqmax_str}) must be >= rfmfreqmin ({rfmfreqmin_str})", file=sys.stderr)
        return 2
    if rfm_freq_min_s > 0 and rfm_freq_max_s > 0 and rfm_freq_max_s >= 2 * rfm_freq_min_s:
        print(f"Error: rfmfreqmax ({rfmfreqmax_str}) must be < 2 × rfmfreqmin ({rfmfreqmin_str})", file=sys.stderr)
        return 2

    return {
        "rows": args.rows,
        "trc_s": trc_s,
        "tfaw_s": tfaw_s,
        "threshold": args.threshold,
        "rfmabo": rfmabo,
        "runtime_s": runtime_s,
        "rfm_freq_min_s": rfm_freq_min_s,
        "rfm_freq_max_s": rfm_freq_max_s,
        "trfcrfm_s": trfcrfm_s,
        "isoc": isoc,
        "randreset": randreset,
        "seed": args.seed,
        "abo_delay": abo_delay,
        "trc_str": trc_str,
        "tfaw_str": tfaw_str,
        "rfmfreqmin_str": rfmfreqmin_str,
        "rfmfreqmax_str": rfmfreqmax_str,
        "trfcrfm_str": trfcrfm_str,
        "runtime_str": runtime_str,
        "csv": args.csv,
    }
