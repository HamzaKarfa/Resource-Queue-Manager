"""Count only duplicates still waiting for a grant."""


class CountRecurrencePolicy:
    key = "count"

    def on_duplicate(self, *, pending: bool, occurrences: int) -> int:
        return occurrences + 1 if pending else occurrences


class CountRecurrenceProvider:
    key = "count"
    label = "Count pending occurrences"
    description = "Repeated pending requests increment a counter without requeueing."

    def create(self) -> CountRecurrencePolicy:
        return CountRecurrencePolicy()
