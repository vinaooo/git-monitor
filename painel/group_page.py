from gi.repository import Adw, Gdk, GObject, Gtk

from .motion import FlipAnimator
from .ordering import move


class GroupPage(Gtk.Stack):
    """One group's grid of cards, with the live drag-reorder preview (blank slot + FLIP animation)."""

    def __init__(self, name, groups):
        super().__init__()
        self.name, self.groups, self.dragging, self.slots = name, groups, None, {}
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, valign=Gtk.Align.START,
                                min_children_per_line=1, max_children_per_line=4,
                                homogeneous=True, margin_top=12, margin_bottom=12,
                                margin_start=12, margin_end=12)
        self.animator = FlipAnimator(self.flow, self.slots)
        drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        drop.connect('motion', lambda _t, x, y: self.drag_over(x, y) or Gdk.DragAction.MOVE)
        drop.connect('drop', lambda *_: self.drag_dropped() or True)
        self.flow.add_controller(drop)
        self.add_named(Adw.StatusPage(title='Empty group', icon_name='io.github.vina.Painel-symbolic',
                                      description='Add a repository, or drag a card onto this group.'), 'empty')
        self.add_named(Gtk.ScrolledWindow(child=self.flow), 'list')
        self._sync()

    def _sync(self):
        self.set_visible_child_name('list' if self.slots else 'empty')

    def add_slot(self, ident, slot):
        self.slots[ident] = slot
        self.flow.append(slot)
        self._sync()

    def remove_slot(self, ident):
        slot = self.slots.pop(ident)
        self.flow.remove(slot.get_parent())  # FlowBoxChild
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
        self.dragging = ident

    def drag_over(self, x, y):
        child = self.flow.get_child_at_pos(x, y)
        if self.dragging and child and child.get_child().card.ident != self.dragging:
            order = move(self._flow_order(), self.dragging, child.get_child().card.ident)
            self.animator.run(lambda: self._show_order(order, self.dragging))

    def drag_dropped(self):
        if self.dragging:
            self.groups.set_order(self.name, self._flow_order())

    def drag_finished(self):
        self.dragging = None
        saved = [r for r in self.groups.repos(self.name) if r in self.slots]
        if saved and self._flow_order() != saved:  # drag cancelled: undo the preview
            self.animator.run(lambda: self._show_order(saved, saved[0]))
