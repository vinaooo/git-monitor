import gi
gi.require_version('Graphene', '1.0')
from gi.repository import Adw, Gdk, Graphene, Gtk

from .ordering import deltas

DURATION_MS = 220


class Slot(Gtk.Box):
    """Wraps a card; paints it displaced by `offset` without touching layout (FLIP animation)."""

    def __init__(self, card):
        super().__init__()
        self.card, self.offset = card, (0.0, 0.0)
        self.append(card)

    def set_offset(self, dx, dy):
        self.offset = (dx, dy)
        self.queue_draw()

    def do_snapshot(self, snapshot):
        snapshot.save()
        snapshot.translate(Graphene.Point().init(*self.offset))
        self.snapshot_child(self.card, snapshot)
        snapshot.restore()


class FlipAnimator:
    """run(change): after `change` re-sequences the flow, glide each moved card from its old spot."""

    def __init__(self, flow, slots):
        self.flow, self.slots, self.animation = flow, slots, None

    def _positions(self):
        out = {}
        for ident, slot in self.slots.items():
            ok, bounds = slot.get_parent().compute_bounds(self.flow)  # layout position, ignores offsets
            if ok:
                out[ident] = (bounds.get_x(), bounds.get_y())
        return out

    def run(self, change):
        if self.animation:
            self.animation.pause()
        before = {i: (p[0] + self.slots[i].offset[0], p[1] + self.slots[i].offset[1])  # where it is drawn now
                  for i, p in self._positions().items()}
        change()
        clock = self.flow.get_frame_clock()
        if clock is None:
            return
        handler = []

        def after_layout(_clock):
            clock.disconnect(handler[0])
            moved = deltas(before, self._positions())
            for i, slot in self.slots.items():  # paint start offsets before the first frame
                slot.set_offset(*moved.get(i, (0.0, 0.0)))
            if moved:
                self._animate(moved)

        handler.append(clock.connect_after('layout', after_layout))

    def _animate(self, moved):
        def step(value):
            for i, (dx, dy) in moved.items():
                self.slots[i].set_offset(dx * value, dy * value)

        self.animation = Adw.TimedAnimation.new(self.flow, 1.0, 0.0, DURATION_MS,
                                                Adw.CallbackAnimationTarget.new(step))
        self.animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self.animation.play()
