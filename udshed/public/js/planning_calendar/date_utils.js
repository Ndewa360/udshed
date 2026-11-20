window.Udshed = window.Udshed || {};

window.Udshed.DateUtils = {
    MONTH_LABEL_OPTIONS: { month: "long", year: "numeric" },

    createLocalDate(year, month, day) {
        return new Date(year, month, day, 12, 0, 0);
    },

    addDays(date, days) {
        const result = new Date(date);
        result.setDate(result.getDate() + days);
        return result;
    },

    getMonday(date) {
        const current = new Date(date);
        const day = current.getDay();
        const diff = (day === 0 ? -6 : 1) - day;
        return this.createLocalDate(current.getFullYear(), current.getMonth(), current.getDate() + diff);
    },

    dateValue(date) {
        if (!date) return NaN;
        return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
    },

    monthKey(year, month) {
        return `${year}-${month}`;
    },

    parseMonthValue(value) {
        const [year, month] = String(value || "").split("-").map(Number);
        if (!Number.isInteger(year) || !Number.isInteger(month) || month < 0 || month > 11) return null;
        return { year, month };
    },

    compareMonths(a, b) {
        if (a.year !== b.year) return a.year - b.year;
        return a.month - b.month;
    },

    normalizeMonths(months) {
        const seen = new Set();
        const cleaned = (Array.isArray(months) ? months : [])
            .map((item) => ({ year: Number(item && item.year), month: Number(item && item.month) }))
            .filter((item) => {
                const key = this.monthKey(item.year, item.month);
                if (!Number.isInteger(item.year) || !Number.isInteger(item.month) || item.month < 0 || item.month > 11 || seen.has(key)) return false;
                seen.add(key);
                return true;
            })
            .sort((a, b) => this.compareMonths(a, b));
        if (cleaned.length) return cleaned;
        const now = new Date();
        return Array.from({ length: 12 }, (_, month) => ({ year: now.getFullYear(), month }));
    },

    getMonthRange(months) {
        const list = this.normalizeMonths(months);
        return { first: list[0], last: list[list.length - 1] };
    },

    formatMonthLabel(year, month) {
        return this.createLocalDate(year, month, 1).toLocaleDateString("fr-FR", this.MONTH_LABEL_OPTIONS);
    },

    initMonthPicker(monthPicker, months, selectedValue) {
        if (!monthPicker) return;
        const list = this.normalizeMonths(months);
        monthPicker.innerHTML = "";
        list.forEach((item) => {
            const option = document.createElement("option");
            option.value = this.monthKey(item.year, item.month);
            option.text = this.formatMonthLabel(item.year, item.month);
            monthPicker.appendChild(option);
        });
        const values = list.map((item) => this.monthKey(item.year, item.month));
        monthPicker.value = values.includes(selectedValue) ? selectedValue : values[0];
    },

    updateWeekLabel(currentWeekStart) {
        const label = document.getElementById("week-label");
        if (!label || !currentWeekStart) return;
        const start = new Date(currentWeekStart);
        const end = this.addDays(start, 5);
        const options = { day: "2-digit", month: "long", year: "numeric" };
        label.innerText = `Semaine du ${start.toLocaleDateString("fr-FR", options)} au ${end.toLocaleDateString("fr-FR", options)}`;
    },

    getWeeksOfMonth(year, month) {
        const weeks = [];
        const firstDay = this.createLocalDate(year, month, 1);
        const lastDay = this.createLocalDate(year, month + 1, 0);
        let current = this.getMonday(firstDay);
        while (this.dateValue(current) <= this.dateValue(lastDay)) {
            if (this.dateValue(this.addDays(current, 5)) >= this.dateValue(firstDay)) {
                weeks.push(new Date(current));
            }
            current = this.addDays(current, 7);
        }
        return weeks;
    },

    getFirstWeekInsideMonth(weeks, year, month) {
        if (Array.isArray(weeks) && weeks.length) return new Date(weeks[0]);
        if (typeof weeks === "number") {
            month = arguments[1];
            year = weeks;
        }
        const firstDay = this.createLocalDate(year, month, 1);
        const monday = this.getMonday(firstDay);
        const weekEnd = this.addDays(monday, 5);
        return this.dateValue(weekEnd) < this.dateValue(firstDay) ? this.addDays(monday, 7) : monday;
    },

    getWeekMonth(weekStart) {
        const thursday = this.addDays(this.getMonday(weekStart), 3);
        return { year: thursday.getFullYear(), month: thursday.getMonth() };
    },

    clampWeekStart(currentWeekStart, months) {
        if (!currentWeekStart) return null;
        const range = this.getMonthRange(months);
        const firstWeek = this.getFirstWeekInsideMonth(range.first.year, range.first.month);
        const lastDay = this.createLocalDate(range.last.year, range.last.month + 1, 0);
        const lastWeek = this.getMonday(lastDay);
        const value = this.dateValue(currentWeekStart);
        if (value < this.dateValue(firstWeek)) return firstWeek;
        if (value > this.dateValue(lastWeek)) return lastWeek;
        return currentWeekStart;
    },

    updateWeekSelect(year, month, weekSelect) {
        if (!weekSelect) return [];
        weekSelect.innerHTML = "";
        const weeks = this.getWeeksOfMonth(year, month);
        weeks.forEach((weekStart, index) => {
            const end = this.addDays(weekStart, 5);
            const option = document.createElement("option");
            option.value = String(weekStart.getTime());
            option.text = `Semaine ${index + 1} : ${weekStart.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" })} - ${end.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" })}`;
            weekSelect.appendChild(option);
        });
        return weeks;
    },

    syncSelectors(weekSelect, monthPicker, currentWeekStart, months) {
        const clamped = this.clampWeekStart(currentWeekStart, months);
        if (!weekSelect || !clamped) return clamped;
        const list = this.normalizeMonths(months);
        const weekMonth = this.getWeekMonth(clamped);
        const value = this.monthKey(weekMonth.year, weekMonth.month);

        if (monthPicker) {
            if (!Array.from(monthPicker.options).some((option) => option.value === value)) {
                const option = document.createElement("option");
                option.value = value;
                option.text = this.formatMonthLabel(weekMonth.year, weekMonth.month);
                monthPicker.appendChild(option);
            }
            monthPicker.value = value;
        }

        const weeks = this.updateWeekSelect(weekMonth.year, weekMonth.month, weekSelect);
        const targetValue = this.dateValue(clamped);
        const selected = weeks.find((weekStart) => this.dateValue(weekStart) === targetValue);
        if (selected) {
            weekSelect.value = String(selected.getTime());
        } else if (weekSelect.options.length) {
            weekSelect.value = weekSelect.options[0].value;
        }
        return clamped;
    }
};
