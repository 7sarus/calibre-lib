#!/usr/bin/env python3
"""Generate the CanMock flowchart as a static PNG."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

# Set up the figure
fig, ax = plt.subplots(1, 1, figsize=(14, 10))
ax.set_xlim(0, 14)
ax.set_ylim(0, 10)
ax.set_aspect('equal')
ax.axis('off')

# Define colors for each subgraph
colors = {
    'official': '#FF6B6B',      # tomato red
    'canmock_pro': '#4ECDC4',   # teal
    'canmock_nightly': '#96CEB4', # light green
    'edge': '#FFFFFF',          # white
}

# Box definitions: (text, x, y, w, h, color, label_key)
# Official subgraph (x from 1 to 4)
official_boxes = [
    ("O1\nOfficial UI\n& Remote\nLogin Gate", 1, 7, 2, 1.5, colors['official']),
    ("O2\nCloud\nEndpoints", 1, 5, 2, 1.5, colors['official']),
    ("O3\nAuth/JWT", 1, 3, 2, 1.5, colors['official']),
    ("O4\nLiveFeed\nSpawns", 1, 1, 2, 1.5, colors['official']),
    ("O5\nTelemetry &\nFaults", 3, 7, 2, 1.5, colors['official']),
    ("O6\nDynamic\nAgent\nDownload", 3, 5, 2, 1.5, colors['official']),
    ("O7\npokemod-injector", 3, 3, 2, 1.5, colors['official']),
    ("O8\nGame Target", 3, 1, 2, 1.5, colors['official']),
]

# CanMock Pro subgraph (x from 5 to 8)
canmock_pro_boxes = [
    ("P1\nCanMock UI\n(v0.86)", 5, 7, 2, 1.5, colors['canmock_pro']),
    ("P2\nOfflineAgents\n(Asset\nExtractor)", 5, 5, 2.5, 1.5, colors['canmock_pro']),
    ("P3\nBundled\nDecrypted\nPro Agents", 5, 3, 2.5, 1.5, colors['canmock_pro']),
    ("P4\nBackground\nLoop: hb.sh", 8, 7, 2, 1.5, colors['canmock_pro']),
    ("P5\nLocal Responder\n(busybox\nhttpd :9000)", 8, 5, 2, 1.5, colors['canmock_pro']),
    ("P6\nHAL Service\n127.0.0.1:9000", 8, 3, 2, 1.5, colors['canmock_pro']),
    ("P7\npokemod-injector", 8, 1, 2, 1.5, colors['canmock_pro']),
    ("P8\nGame Target\n(com.nianticlabs.pokemongo)", 8, -1, 2, 1.5, colors['canmock_pro']),
]

# CanMock Nightly subgraph (x from 9 to 14)
canmock_nightly_boxes = [
    ("N1\nCanMock Nightly\nUI", 9, 7, 2.5, 1.5, colors['canmock_nightly']),
    ("N2\nOfflineAgents\n(Asset\nExtractor)", 9, 5, 2.5, 1.5, colors['canmock_nightly']),
    ("N3\nPre-Patched\nAgent Assets", 9, 3, 2.5, 1.5, colors['canmock_nightly']),
    ("N4\nZero Local\nListeners\n(No :9000)", 12, 7, 2, 1.5, colors['canmock_nightly']),
    ("N5\nHAL Service\noffline.invalid", 12, 5, 2, 1.5, colors['canmock_nightly']),
    ("N6\npokemod-injector", 12, 3, 2, 1.5, colors['canmock_nightly']),
    ("N7\nGame Target", 12, 1, 2, 1.5, colors['canmock_nightly']),
    ("N8\nLiveFeed\nShort-Circuited", 12, -1, 2, 1.5, colors['canmock_nightly']),
    ("N9\nHeartbeat\nNeutered", 14, 3, 2, 1.5, colors['canmock_nightly']),
    ("N10\nTelemetry\nBlocked\n(Empty Token)", 14, 1, 2, 1.5, colors['canmock_nightly']),
]

# Draw all boxes
all_box_defs = []
for text, x, y, w, h, color in official_boxes:
    rect = patches.Rectangle((x, y), w, h, 
                              linewidth=2, edgecolor='black', facecolor=color, alpha=0.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, 
            ha='center', va='center', fontsize=7.5, fontweight='bold', 
            wrap=True)
    all_box_defs.append(('official', x, y, w, h, text, color))

for text, x, y, w, h, color in canmock_pro_boxes:
    rect = patches.Rectangle((x, y), w, h, 
                              linewidth=2, edgecolor='black', facecolor=color, alpha=0.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, 
            ha='center', va='center', fontsize=7.5, fontweight='bold', 
            wrap=True)
    all_box_defs.append(('canmock_pro', x, y, w, h, text, color))

for text, x, y, w, h, color in canmock_nightly_boxes:
    rect = patches.Rectangle((x, y), w, h, 
                              linewidth=2, edgecolor='black', facecolor=color, alpha=0.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, 
            ha='center', va='center', fontsize=7.5, fontweight='bold', 
            wrap=True)
    all_box_defs.append(('canmock_nightly', x, y, w, h, text, color))

# Draw edges - Official subgraph
# O1 -> O2, O2 -> O3, O2 -> O4, O2 -> O5, O6 -> O7, O7 -> O8
official_edges = [
    ((1+1, 7+0.75), (1+1, 5+1.25)),   # O1 -> O2
    ((1+1, 5+0.25), (1+1, 3+1.25)),   # O2 -> O3
    ((1+1, 5+1.25), (1+1, 1+1.25)),   # O2 -> O4
    ((1+1+2, 5+0.75), (3+1, 7+0.25)), # O2 -> O5
    ((1+1+2, 5+1.25), (3+1, 5+0.25)), # O2 -> O6
    ((3+1+2, 5+0.75), (3+1+2, 3+1.25)), # O6 -> O7
    ((3+1+2, 3+0.25), (3+1+2, 1+1.25)), # O7 -> O8
]

# CanMock Pro edges
# P1 -> P2, P2 -> P3, P1 -> P6 -> P5, P3 -> P7 -> P8, P8 ->|Heartbeat| P5
canmock_pro_edges = [
    ((5+1, 7+0.75), (5+1+2, 5+0.25)),   # P1 -> P2
    ((5+1+2.5, 5+0.75), (5+1+2.5, 3+1.25)), # P2 -> P3
    ((5+1, 7+1.25), (8+1, 3+0.25)),     # P1 -> P6
    ((8+1+2, 3+0.75), (8+1+2, 5+1.25)), # P6 -> P5
    ((5+1+2.5, 3+0.25), (8+1, 1+1.25)), # P3 -> P7
    ((8+1+2, 1+0.25), (8+1+2, -1+1.25)), # P7 -> P8
    ((8+1+2, -1+0.75), (8+1+2, 5+0.25)), # P8 -> P5 (heartbeat polling)
]

# CanMock Nightly edges
# N1 -> N2, N2 -> N3, N2 -.->|hb.sh Deleted| N4, N1 -> N5 -> N6 -> N7, N7 -> N8,N9,N10
canmock_nightly_edges = [
    ((9+1, 7+0.75), (9+1+2.5, 5+0.25)),   # N1 -> N2
    ((9+1+2.5, 3+0.75), (9+1+2.5, 3+1.25)), # N2 -> N3
    ((9+1+2.5, 7+0.25), (12, 7+0.75)),    # N2 -.->|hb.sh Deleted| N4
    ((9+1, 7+1.25), (12+1, 5+0.25)),      # N1 -> N5
    ((12+1+2, 5+0.75), (12+1+2, 3+1.25)), # N5 -> N6
    ((12+1+2, 3+0.25), (12+1+2, 1+1.25)), # N6 -> N7
    ((12+1+2, 1+0.25), (12+1+2, -1+1.25)), # N7 -> N8
    ((12+1+2, 1+0.75), (14, 3+0.25)),     # N7 -> N9
    ((12+1+2, 1+1.25), (14, 1+0.75)),     # N7 -> N10
]

# Draw all edges
all_edges = official_edges + canmock_pro_edges + canmock_nightly_edges

for start, end in all_edges:
    ax.annotate('', xy=end, xytext=start,
                arrowprops=dict(arrowstyle='-|>', color='black', lw=1.5))

# Add subgraph labels
ax.text(2, 9.5, 'Official Pokemod (com.pokemod.app.public)', 
        ha='center', va='center', fontsize=11, fontweight='bold', color='red')
ax.text(6.5, 9.5, 'CanMock Pro (com.can.mock)', 
        ha='center', va='center', fontsize=11, fontweight='bold', color='teal')
ax.text(11.5, 9.5, 'CanMock Nightly (com.can.mock.nightly)', 
        ha='center', va='center', fontsize=11, fontweight='bold', color='green')

# Add version/info
ax.text(0.5, 0.5, 'CanMock Flowchart — Official / Pro / Nightly', 
        ha='left', va='bottom', fontsize=9, style='italic')

# Adjust layout and save
plt.tight_layout()
plt.savefig('/home/thomas/Projects/calibre-lib/flowchart.png', dpi=150, bbox_inches='tight', 
            facecolor='white')
print("Saved flowchart.png")
plt.close()
print("Done — PNG generated at /home/thomas/Projects/calibre-lib/flowchart.png")