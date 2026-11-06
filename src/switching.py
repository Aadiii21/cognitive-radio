class SwitchingDelay:
    """Track transmission steps lost during a channel-switch interruption."""

    def __init__(self, delay_steps=2):
        if delay_steps < 0:
            raise ValueError("delay_steps cannot be negative.")

        self.delay_steps = delay_steps
        self.remaining_steps = 0

    @property
    def is_active(self):
        return self.remaining_steps > 0

    def start(self):
        """Begin a switching interruption."""
        self.remaining_steps = self.delay_steps

    def consume_step(self):
        """
        Consume one time step.

        Returns True if this step is unavailable for transmission.
        """
        if not self.is_active:
            return False

        self.remaining_steps -= 1
        return True
