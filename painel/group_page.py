import logging

from gi.repository import Adw, Gdk, GObject, Gtk

from .motion import FlipAnimator
from .ordering import move

log = logging.getLogger('painel.drag')


class GroupPage(Gtk.Stack):
    """One group's grid of cards, with the live drag-reorder preview (blank slot + FLIP animation)."""

    def __init__(self, name, groups, can_reorder=lambda: True):
        super().__init__()
        self.name, self.groups, self.dragging, self.slots = name, groups, None, {}
        self.can_reorder, self.compact = can_reorder, False
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, valign=Gtk.Align.START,
                                min_children_per_line=1, max_children_per_line=4,
                                homogeneous=True, margin_top=12, margin_bottom=12,
                                margin_start=12, margin_end=12)
        self.animator = FlipAnimator(self.flow, self.slots)
        drop = Gtk.DropTarget.new(GObject.TYPE_VARIANT, Gdk.DragAction.MOVE)
        drop.connect('motion', lambda _t, x, y: self.drag_over(x, y) or Gdk.DragAction.MOVE)
        drop.connect('drop', lambda *_: self.drag_dropped() or bool(self.dragging))
        self.add_controller(drop)  # whole page, not just the cards: margins and gaps must not cancel the drop
        self.add_named(Adw.StatusPage(title='Empty group', icon_name='io.github.vina.Painel-symbolic',
                                      description='Add a repository, or drag a card onto this group.'), 'empty')
        self.add_named(Gtk.ScrolledWindow(child=self.flow), 'list')
        self._sync()

    def _sync(self):
        self.set_visible_child_name('list' if self.slots else 'empty')

    def add_slot(self, ident, slot):
        self.slots[ident] = slot
        slot.card.set_compact(self.compact)
        self.flow.append(slot)
        self._sync()

    def remove_slot(self, ident):
        slot = self.slots.pop(ident)
        wrapper = slot.get_parent()  # FlowBoxChild
        wrapper.set_child(None)  # free the slot first, else re-adding it elsewhere trips a GTK assertion
        self.flow.remove(wrapper)
        self._sync()
        return slot

    def _flow_order(self):
        order, child = [], self.flow.get_first_child()
        while child:
            order.append(child.get_child().card.ident)
            child = child.get_next_sibling()
        return order

    def _show_order(self, order, anchor):
        """Re-sequence the flow without reparenting `anchor` (moving the drag source would abort the drag)."""
        children = {i: self.slots[i].get_parent() for i in order}
        for i in order:
            if i != anchor:
                self.flow.remove(children[i])
        pos = order.index(anchor)
        for n, i in enumerate(order):
            if i == anchor:
                continue
            self.flow.insert(children[i], n) if n < pos else self.flow.append(children[i])

    def drag_started(self, ident):
        log.debug('drag started: %s', ident)
        self.dragging = ident

    def _card_slot_at(self, x, y):
        """Our FlowBoxChild nearest to (x, y) in page coordinates, so margins and gaps (e.g. above the first row)
        still target a card. get_child_at_pos can hand back a FlowBoxChild of a *nested* FlowBox (the card's
        chips), so we measure our own direct children instead."""
        point = self.translate_coordinates(self.flow, x, y)
        if not point:
            return None
        px, py = point
        best, child = None, self.flow.get_first_child()
        while child:
            ok, b = child.compute_bounds(self.flow)
            if ok:
                dx = max(b.get_x() - px, 0, px - b.get_x() - b.get_width())
                dy = max(b.get_y() - py, 0, py - b.get_y() - b.get_height())
                if best is None or dx * dx + dy * dy < best[0]:
                    best = (dx * dx + dy * dy, child)
            child = child.get_next_sibling()
        return best and best[1]

    def drag_over(self, x, y):
        if not self.can_reorder():  # a sort mode owns the order
            return
        child = self._card_slot_at(x, y)
        target = child and child.get_child().card.ident
        if self.dragging and target and target != self.dragging:
            order = move(self._flow_order(), self.dragging, target)
            log.debug('over %s: preview %s', target, [i[-8:] for i in order])
            self.animator.run(lambda: self._show_order(order, self.dragging))

    def drag_dropped(self):
        log.debug('drop: dragging=%s can_reorder=%s order=%s', self.dragging, self.can_reorder(),
                  [i[-8:] for i in self._flow_order()])
        if self.dragging and self.can_reorder():
            self.groups.set_order(self.name, self._flow_order())

    def drag_finished(self):
        log.debug('drag finished: dragging=%s stored=%s', self.dragging, self.groups.repos(self.name))
        self.dragging = None
        saved = [r for r in self.groups.repos(self.name) if r in self.slots]
        if self.can_reorder() and saved and self._flow_order() != saved:  # drag cancelled: undo the preview
            self.animator.run(lambda: self._show_order(saved, saved[0]))

    def apply_order(self, order):
        """Show `order` (animated); ignored while a drag is previewing its own order."""
        order = [i for i in order if i in self.slots]
        if order and not self.dragging and order != self._flow_order():
            self.animator.run(lambda: self._show_order(order, order[0]))

    def set_view(self, max_columns, compact):
        self.flow.set_max_children_per_line(max_columns)
        self.compact = compact
        for slot in self.slots.values():
            slot.card.set_compact(compact)
