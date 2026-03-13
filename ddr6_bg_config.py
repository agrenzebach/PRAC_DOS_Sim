# DDR5 DRAM Protocol Configuration for Activates across Bank Groups
# Based on DDR6 AC Timing Parameter R7  tRRD_S = 1.875ns and tFAW = 7.5ns

trc = "2.5ns"        # tRC timing between activates
rfmabo = 4          # MR71:OP[1:0] — valid values: 1, 2, 4 (also sets abo_delay = rfmabo)
trfcrfm = "400ns"   # tRFMab = 5*tRRFab
refw = "32ms"
isoc = 0
rfmfreqmin = "0us"
rfmfreqmax = "0us"
