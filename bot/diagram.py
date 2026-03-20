"""State machine diagram generator using Pillow.

Exposes:
  generate_png() -> bytes     — renders the diagram, returns raw PNG bytes
  cached_file_id: str | None  — set by message.py after first Telegram upload
"""
import io
import math

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
COL_BG       = (255, 255, 255)
COL_TEXT     = ( 20,  20,  20)
COL_BORDER   = ( 80,  80,  80)
COL_ARROW    = ( 60,  60,  60)
COL_LABEL    = ( 40,  40,  40)
COL_DRAFT    = (220, 220, 220)
COL_PENDING  = (173, 216, 230)
COL_APPROVED = (144, 238, 144)
COL_REJECTED = (255, 160, 122)
COL_REVISION = (255, 200, 100)

# ---------------------------------------------------------------------------
# Node data:  state_key -> (cx, cy, fill_colour)
# Box dimensions shared across all nodes
# ---------------------------------------------------------------------------
BW, BH = 180, 52   # box width, box height

NODES: dict[str, tuple[int, int, tuple[int, int, int]]] = {
    "draft":               (450,   80, COL_DRAFT),
    "pending_ippt":        (180,  240, COL_PENDING),
    "pending_pc":          (450,  340, COL_PENDING),
    "revision_requested":  (180,  520, COL_REVISION),
    "rejected":            (720,  460, COL_REJECTED),
    "pending_oc":          (450,  660, COL_PENDING),
    "oc_approved":         (450,  820, COL_APPROVED),
    "pending_co":          (450,  960, COL_PENDING),
    "approved":            (450, 1120, COL_APPROVED),
    "co_rejected":         (180,  960, COL_REVISION),
}

# User-friendly display labels for each state
NODE_LABELS: dict[str, str] = {
    "draft":               "Filling in\nyour application",
    "pending_ippt":        "Submitted - complete\nIPPT first",
    "pending_pc":          "Waiting for\nPC review",
    "revision_requested":  "Changes requested -\nre-upload docs",
    "rejected":            "Rejected",
    "pending_oc":          "Waiting for\nOC review",
    "oc_approved":         "OC Approved -\nApply on OneNS",
    "pending_co":          "Waiting for\nCO decision",
    "approved":            "Approved",
    "co_rejected":         "CO Rejected -\nre-upload & resubmit",
}

# (from_state, to_state, label, route_hint)
EDGES: list[tuple[str, str, str, str]] = [
    ("draft",               "pending_pc",          "You submit (/confirm)",          "diag_right"),
    ("draft",               "pending_ippt",         "You submit - IPPT not done",    "diag_left"),
    ("pending_ippt",        "pending_pc",           "You update IPPT (/edit_ippt)",  "diag_right"),
    ("pending_pc",          "pending_oc",           "PC approves",                   "straight"),
    ("pending_pc",          "rejected",             "PC rejects",                    "right"),
    ("pending_pc",          "revision_requested",   "PC requests changes",           "left"),
    ("revision_requested",  "pending_pc",           "You re-upload docs",            "loop_up"),
    ("pending_oc",          "oc_approved",          "OC approves",                   "straight"),
    ("pending_oc",          "rejected",             "OC rejects",                    "right"),
    ("pending_oc",          "revision_requested",   "OC requests changes",           "left"),
    ("revision_requested",  "pending_oc",           "You re-upload docs",            "loop_down"),
    ("oc_approved",         "pending_co",           "You apply on OneNS (/applied)", "straight"),
    ("pending_co",          "approved",             "CO approves",                   "straight"),
    ("pending_co",          "co_rejected",          "CO rejects",                    "left"),
    ("co_rejected",         "pending_oc",           "You resubmit (/resubmit)",      "up"),
]

# Module-level file_id cache (populated by message.py on first send)
cached_file_id: str | None = None


# ---------------------------------------------------------------------------
# Private drawing helpers
# ---------------------------------------------------------------------------

def _box_edges(state: str) -> dict[str, tuple[int, int]]:
    """Return the four cardinal edge midpoints of a node's box."""
    cx, cy, _ = NODES[state]
    return {
        "top":    (cx,         cy - BH // 2),
        "bottom": (cx,         cy + BH // 2),
        "left":   (cx - BW // 2, cy),
        "right":  (cx + BW // 2, cy),
    }


def _draw_arrowhead(draw, tip_x: int, tip_y: int, dx: float, dy: float) -> None:
    """Draw a small filled arrowhead at (tip_x, tip_y) pointing in direction (dx,dy)."""
    length = math.hypot(dx, dy)
    if length == 0:
        return
    ux, uy = dx / length, dy / length       # unit vector along arrow direction
    px, py = -uy, ux                        # perpendicular unit vector
    size = 10
    base_x = tip_x - ux * size
    base_y = tip_y - uy * size
    p1 = (int(tip_x), int(tip_y))
    p2 = (int(base_x + px * size * 0.45), int(base_y + py * size * 0.45))
    p3 = (int(base_x - px * size * 0.45), int(base_y - py * size * 0.45))
    draw.polygon([p1, p2, p3], fill=COL_ARROW)


def _draw_polyline(draw, points: list[tuple[int, int]]) -> None:
    """Draw a polyline through the given points and an arrowhead at the last segment."""
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=COL_ARROW, width=2)
    # Arrowhead at the final point, pointing along the last segment
    if len(points) >= 2:
        x0, y0 = points[-2]
        x1, y1 = points[-1]
        _draw_arrowhead(draw, x1, y1, x1 - x0, y1 - y0)


def _midpoint(points: list[tuple[int, int]]) -> tuple[int, int]:
    """Return the midpoint of the longest segment in the polyline."""
    best_len = -1
    best_mid = points[len(points) // 2]
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        seg_len = math.hypot(x1 - x0, y1 - y0)
        if seg_len > best_len:
            best_len = seg_len
            best_mid = ((x0 + x1) // 2, (y0 + y1) // 2)
    return best_mid


def _draw_edge_label(draw, points: list[tuple[int, int]], label: str, font) -> None:
    """Draw the transition label near the midpoint of the longest segment."""
    mx, my = _midpoint(points)
    # Offset slightly so text doesn't sit on the line
    mx += 6
    my -= 10
    # Draw a small white background behind the text for readability
    bbox = font.getbbox(label)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.rectangle(
        [mx - 2, my - 2, mx + tw + 2, my + th + 2],
        fill=(255, 255, 255),
    )
    draw.text((mx, my), label, fill=COL_LABEL, font=font)


def _compute_waypoints(from_state: str, to_state: str, hint: str) -> list[tuple[int, int]]:
    """Compute the list of waypoints for an edge given its routing hint."""
    fe = _box_edges(from_state)
    te = _box_edges(to_state)

    if hint == "straight":
        return [fe["bottom"], te["top"]]

    elif hint == "diag_right":
        # From bottom-right area of from-box to top-left area of to-box
        fcx, fcy, _ = NODES[from_state]
        tcx, tcy, _ = NODES[to_state]
        # Start at bottom-right of from, end at top of to
        start = (fcx + BW // 4, fcy + BH // 2)
        end   = te["top"]
        return [start, end]

    elif hint == "diag_left":
        fcx, fcy, _ = NODES[from_state]
        tcx, tcy, _ = NODES[to_state]
        start = (fcx - BW // 4, fcy + BH // 2)
        end   = te["top"]
        return [start, end]

    elif hint == "right":
        # Horizontal rightward: exit right side of from, enter left or top of to
        start = fe["right"]
        # Destination may be above or below — use a 2-segment elbow
        tcx, tcy, _ = NODES[to_state]
        fcx, fcy, _ = NODES[from_state]
        mid_x = (start[0] + (tcx - BW // 2)) // 2
        mid_y = start[1]
        elbow = (mid_x, mid_y)
        end   = (tcx - BW // 2, tcy)   # left side of destination
        return [start, elbow, end]

    elif hint == "left":
        # Horizontal leftward: exit left side of from, enter right side of to
        start = fe["left"]
        tcx, tcy, _ = NODES[to_state]
        end   = (tcx + BW // 2, tcy)   # right side of destination
        mid_x = (start[0] + tcx + BW // 2) // 2
        elbow = (mid_x, start[1])
        return [start, elbow, end]

    elif hint == "loop_up":
        # revision_requested → pending_pc: exit left, jog far left, go up, enter left of pending_pc
        start = fe["left"]
        jog_x = 50
        p1 = (jog_x, start[1])
        tcx, tcy, _ = NODES[to_state]
        p2 = (jog_x, tcy)
        end = (tcx - BW // 2, tcy)
        return [start, p1, p2, end]

    elif hint == "loop_down":
        # revision_requested → pending_oc: exit left, jog far left, go down, enter left of pending_oc
        start = fe["left"]
        jog_x = 40
        p1 = (jog_x, start[1])
        tcx, tcy, _ = NODES[to_state]
        p2 = (jog_x, tcy)
        end = (tcx - BW // 2, tcy)
        return [start, p1, p2, end]

    elif hint == "up":
        # co_rejected → pending_oc: straight up (with slight x offset to avoid overlapping)
        fcx, fcy, _ = NODES[from_state]
        tcx, tcy, _ = NODES[to_state]
        start = (fcx, fcy - BH // 2)           # top of co_rejected
        end   = (tcx - BW // 4, tcy + BH // 2) # bottom-left area of pending_oc
        return [start, end]

    else:
        # Fallback: direct line
        return [fe["bottom"], te["top"]]


def _draw_box(draw, state: str, font) -> None:
    cx, cy, fill = NODES[state]
    x0, y0 = cx - BW // 2, cy - BH // 2
    x1, y1 = cx + BW // 2, cy + BH // 2
    draw.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=fill, outline=COL_BORDER, width=2)
    label = NODE_LABELS.get(state, state.replace("_", " "))
    if "\n" in label:
        draw.multiline_text((cx, cy), label, fill=COL_TEXT,
                            font=font, anchor="mm", align="center", spacing=2)
    else:
        draw.text((cx, cy), label, fill=COL_TEXT, font=font, anchor="mm")


def _draw_legend(draw, W: int, H: int, font) -> None:
    items = [
        ("Draft",           COL_DRAFT),
        ("Pending",         COL_PENDING),
        ("Approved",        COL_APPROVED),
        ("Rejected",        COL_REJECTED),
        ("Revision/CO rej", COL_REVISION),
    ]
    sq = 14
    gap = 10
    total_w = sum(sq + gap + int(font.getlength(lbl)) + gap for lbl, _ in items)
    x = (W - total_w) // 2
    y = H - 30
    for lbl, col in items:
        draw.rectangle([x, y, x + sq, y + sq], fill=col, outline=COL_BORDER, width=1)
        draw.text((x + sq + 4, y + 1), lbl, fill=COL_TEXT, font=font)
        x += sq + gap + int(font.getlength(lbl)) + gap


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_png() -> bytes:
    """Render the NS Deferment state machine as a PNG and return raw bytes."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 900, 1230

    img = Image.new("RGB", (W, H), COL_BG)
    draw = ImageDraw.Draw(img)

    font_title = ImageFont.load_default(size=17)
    font_node  = ImageFont.load_default(size=13)
    font_label = ImageFont.load_default(size=11)

    # Title
    draw.text((W // 2, 18), "NS Deferment - Your Application Journey",
              fill=COL_TEXT, font=font_title, anchor="mt")

    # Pre-compute waypoints for all edges
    all_edges_wp = [
        (_compute_waypoints(fr, to, hint), label)
        for fr, to, label, hint in EDGES
    ]

    # 1. Draw arrow lines and arrowheads first
    for waypoints, _ in all_edges_wp:
        _draw_polyline(draw, waypoints)

    # 2. Draw boxes on top (covers arrow tails/entry points cleanly)
    for state in NODES:
        _draw_box(draw, state, font_node)

    # 3. Draw edge labels last -- sit on top of boxes so they're always visible
    for waypoints, label in all_edges_wp:
        _draw_edge_label(draw, waypoints, label, font_label)

    # 4. Legend
    _draw_legend(draw, W, H, font_label)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
