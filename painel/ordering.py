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
