window.Udshed = window.Udshed || {};

window.Udshed.DateUtils = {
    createLocalDate(year, month, day) {
        return new Date(year, month, day, 12, 0, 0);
    },

    getMonday(date) {
        const current = new Date(date);
        const day = current.getDay();
        const diff = (day === 0 ? -6 : 1) - day;
        current.setDate(current.getDate() + diff);
        return Udshed.DateUtils.createLocalDate(current.getFullYear(), current.getMonth(), current.getDate());
    },

    updateWeekLabel(currentWeekStart) {
        const label = document.getElementById("week-label");
        if (!label || !currentWeekStart) return;
        const start = new Date(currentWeekStart);
        const end = new Date(start);
        end.setDate(start.getDate() + 5);
        const options = { day: "2-digit", month: "long", year: "numeric" };
        label.innerText = `Semaine du ${start.toLocaleDateString("fr-FR", options)} au ${end.toLocaleDateString("fr-FR", options)}`;
    },

    initMonthPicker(monthPicker) {
        if (!monthPicker) return;
        const now = new Date();
        monthPicker.innerHTML = "";
        for (let year = now.getFullYear() - 1; year <= now.getFullYear() + 1; year++) {
            for (let month = 0; month < 12; month++) {
                const option = document.createElement("option");
                option.value = `${year}-${month}`;
                option.text = new Date(year, month, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
                if (year === now.getFullYear() && month === now.getMonth()) option.selected = true;
                monthPicker.appendChild(option);
            }
        }
    },

    getWeeksOfMonth(year, month) {
        const weeks = [];
        const firstDay = Udshed.DateUtils.createLocalDate(year, month, 1);
        const lastDay = Udshed.DateUtils.createLocalDate(year, month + 1, 0);
        const current = Udshed.DateUtils.getMonday(firstDay);
        while (current <= lastDay) {
            weeks.push(new Date(current));
            current.setDate(current.getDate() + 7);
        }
        return weeks;
    },

    updateWeekSelect(year, month, weekSelect) {
        if (!weekSelect) return;
        weekSelect.innerHTML = "";
        const weeks = Udshed.DateUtils.getWeeksOfMonth(year, month);
        weeks.forEach((weekStart, index) => {
            const end = new Date(weekStart);
            end.setDate(weekStart.getDate() + 5);
            const option = document.createElement("option");
            option.value = weekStart.getTime();
            option.text = `Semaine ${index + 1} : ${weekStart.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" })} - ${end.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" })}`;
            weekSelect.appendChild(option);
        });
    },

    getFirstWeekInsideMonth(weeks, year, month) {
        const found = (weeks || []).find((weekStart) => {
            const weekEnd = new Date(weekStart);
            weekEnd.setDate(weekStart.getDate() + 6);
            return weekStart.getMonth() === month || weekEnd.getMonth() === month;
        });
        return found || (weeks && weeks.length ? weeks[0] : Udshed.DateUtils.createLocalDate(year, month, 1));
    },

    syncSelectors(weekSelect, monthPicker, currentWeekStart) {
        if (!weekSelect || !currentWeekStart) return;
        const year = currentWeekStart.getFullYear();
        const month = currentWeekStart.getMonth();
        if (monthPicker) {
            const value = `${year}-${month}`;
            if (!Array.from(monthPicker.options).some((option) => option.value === value)) {
                const option = document.createElement("option");
                option.value = value;
                option.text = new Date(year, month, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
                monthPicker.appendChild(option);
            }
            monthPicker.value = value;
        }
        Udshed.DateUtils.updateWeekSelect(year, month, weekSelect);
        const weekValue = String(currentWeekStart.getTime());
        if (Array.from(weekSelect.options).some((option) => option.value === weekValue)) {
            weekSelect.value = weekValue;
        } else if (weekSelect.options.length) {
            weekSelect.value = weekSelect.options[0].value;
        }
    }
};
