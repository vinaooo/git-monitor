def move(order, src, dst):
    """New list with `src` taken out and placed at `dst`'s position (drag-and-drop semantics)."""
    if src == dst or src not in order or dst not in order:
        return list(order)
    result = [x for x in order if x != src]
    result.insert(order.index(dst), src)
    return result


def deltas(before, after, eps=0.5):
    """FLIP offsets {id: (dx, dy)} = old position - new position, for ids that moved more than eps."""
    out = {}
    for i in before.keys() & after.keys():
        dx, dy = before[i][0] - after[i][0], before[i][1] - after[i][1]
        if abs(dx) > eps or abs(dy) > eps:
            out[i] = (dx, dy)
    return out


def slot_at(centers, y):
    """Index of the row center nearest to y."""
    return min(range(len(centers)), key=lambda i: abs(centers[i] - y))


def shift_offsets(tops, src, dst):
    """Paint offsets previewing the row at `src` moved to `dst` (rows of equal height, tops = layout y)."""
    out = [0] * len(tops)
    for k in range(src + 1, dst + 1):  # dragging down: rows in between move up one slot
        out[k] = tops[k - 1] - tops[k]
    for k in range(dst, src):  # dragging up: they move down one slot
        out[k] = tops[k + 1] - tops[k]
    out[src] = tops[dst] - tops[src]  # the gap sits where the row will land
    return out
