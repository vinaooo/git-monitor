def move(order, src, dst):
    """New list with `src` taken out and placed at `dst`'s position (drag-and-drop semantics)."""
    if src == dst or src not in order or dst not in order:
        return list(order)
    result = [x for x in order if x != src]
    result.insert(order.index(dst), src)
    return result
