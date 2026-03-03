# DDR6 DRAM Protocol Configuration for Activates to single Bank

trc = "63ns"        # tRC timing between activates
rfmabo = 4          # MR71:OP[1:0] — valid values: 1, 2, 4 (also sets abo_delay = rfmabo)
trfcrfm = "400ns"   # tRFMab = 5*tRRFab
refw = "32ms"
isoc = 0
rfmfreqmin = "0us"
rfmfreqmax = "0us"
