"""Legacy idempotence: duplicate requests do not increase occurrences."""


class IgnoreRecurrencePolicy:
    key = "ignore"

    def on_duplicate(self, *, pending: bool, occurrences: int) -> int:
        return occurrences


class IgnoreRecurrenceProvider:
    key = "ignore"
    label = "Ignore duplicates"
    description = "Keep one request; repeated calls do not increase its count."

    def create(self) -> IgnoreRecurrencePolicy:
        return IgnoreRecurrencePolicy()
