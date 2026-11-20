window.Udshed = window.Udshed || {};

const ROLE_LIST = {
    ADMINISTRATOR: "Administrator",
    SYSTEM_MANAGER: "System Manager",
    COORDINATOR: "Coordonateur",
    PLANNING_MANAGER: "Planning Manager",
    TEACHER: "Teacher",
    STUDENT: "Student"
};

const PLANNING_ROLES = [ROLE_LIST.COORDINATOR, ROLE_LIST.PLANNING_MANAGER];
const ADMIN_ROLES = [ROLE_LIST.ADMINISTRATOR, ROLE_LIST.SYSTEM_MANAGER];
const normalizeValue = (value) => value === null || value === undefined ? null : String(value);
const hasPlanningRole = (roles) => (roles || []).some((role) => PLANNING_ROLES.includes(role));
const valuesOf = (items) => (Array.isArray(items) ? items : [])
    .map((item) => normalizeValue(item && typeof item === "object" ? (item.name || item.value || item) : item))
    .filter(Boolean);

window.Udshed.Perms = {
    normalizeUserContext(userContext) {
        const rows = Array.isArray(userContext) ? userContext : [];
        if (!rows.length) {
            return {
                academic_year: [],
                default_academic_year: null,
                roles: [],
                teacher: null,
                faculty: [],
                filiere: [],
                niveau: [],
                perms: [],
                can_plan: false
            };
        }
        const unique = (values) => [...new Set(values.filter(Boolean))];
        const flatten = (key) => unique(
            rows
                .filter((row) => Array.isArray(row[key]))
                .flatMap((row) => row[key].map((item) => normalizeValue(item && (item.name || item))))
        );
        return {
            academic_year: flatten("academic_year_list"),
            default_academic_year: rows[0].default_academic_year || null,
            roles: unique(rows.map((row) => row.role)),
            teacher: rows.find((row) => row.teacher)?.teacher || null,
            faculty: flatten("faculty"),
            filiere: flatten("filiere"),
            niveau: flatten("niveau"),
            perms: rows,
            can_plan: unique(rows.map((row) => row.role)).some((role) =>
                [ROLE_LIST.ADMINISTRATOR, ROLE_LIST.SYSTEM_MANAGER, ROLE_LIST.COORDINATOR, ROLE_LIST.PLANNING_MANAGER].includes(role)
            )
        };
    },

    is_admin(userContext) {
        if (!userContext) return false;
        const roles = userContext.roles || [];
        return roles.some((role) => ADMIN_ROLES.includes(role));
    },

    should_apply_filter(userContext) {
        return !this.is_admin(userContext);
    },

    user_can_plan(userContext) {
        if (!userContext) return false;
        if (this.is_admin(userContext)) return true;
        return (userContext.perms || []).some((perm) =>
            PLANNING_ROLES.includes(perm.role) && valuesOf(perm.filiere).length > 0 && valuesOf(perm.niveau).length > 0
        );
    },

    default_planning_scope(userContext) {
        if (!userContext) return {};
        const academic_year = normalizeValue(userContext.default_academic_year || userContext.academic_year?.[0]);
        if (this.is_admin(userContext)) {
            return { academic_year, faculty: null, filiere: null, niveau: null, teacher: null };
        }
        const planningPerm = (userContext.perms || []).find((perm) =>
            PLANNING_ROLES.includes(perm.role) && valuesOf(perm.filiere).length && valuesOf(perm.niveau).length
        );
        if (planningPerm) {
            const filiereItem = (planningPerm.filiere || []).find(Boolean);
            return {
                academic_year: normalizeValue(planningPerm.academic_year_list?.[0]?.name || planningPerm.academic_year_list?.[0]) || academic_year,
                faculty: normalizeValue(filiereItem && filiereItem.faculte) || normalizeValue(userContext.faculty[0]),
                filiere: normalizeValue(filiereItem && (filiereItem.name || filiereItem)),
                niveau: normalizeValue((planningPerm.niveau || [])[0] && ((planningPerm.niveau || [])[0].name || (planningPerm.niveau || [])[0]))
            };
        }
        return {
            academic_year,
            faculty: null,
            filiere: null,
            niveau: null,
            teacher: normalizeValue(userContext.teacher)
        };
    },

    allowed_levels_for_filiere(userContext, filiere) {
        const target = normalizeValue(filiere);
        if (!target || !userContext) return [];
        const values = (userContext.perms || [])
            .filter((perm) => valuesOf(perm.filiere).includes(target))
            .flatMap((perm) => valuesOf(perm.niveau));
        return [...new Set(values)];
    },

    combine_get_query(base, extra) {
        if (!base && !extra) return undefined;
        return () => {
            const left = typeof base === "function" ? (base() || {}) : {};
            const right = typeof extra === "function" ? (extra() || {}) : {};
            return {
                ...left,
                ...right,
                filters: { ...(left.filters || {}), ...(right.filters || {}) }
            };
        };
    },

    user_can_edit_planning_cell(cellFilter, userContext) {
        if (!userContext) return false;
        if (this.is_admin(userContext)) return true;
        const filter = cellFilter || {};
        const hasScopeFilter = Boolean(filter.filiere || filter.niveau || filter.academic_year);
        if (!hasScopeFilter) return this.user_can_plan(userContext);
        if (!hasPlanningRole(userContext.roles)) return false;
        const perms = (userContext.perms || []).filter((perm) => {
            if (!PLANNING_ROLES.includes(perm.role)) return false;
            if (filter.academic_year && !valuesOf(perm.academic_year_list).includes(normalizeValue(filter.academic_year))) return false;
            if (filter.filiere && !valuesOf(perm.filiere).includes(normalizeValue(filter.filiere))) return false;
            if (filter.niveau) {
                const allowed = filter.filiere
                    ? valuesOf(perm.niveau).filter((niveau) => valuesOf(perm.filiere).includes(normalizeValue(filter.filiere)))
                    : valuesOf(perm.niveau);
                if (!allowed.includes(normalizeValue(filter.niveau))) return false;
            }
            return true;
        });
        return perms.length > 0;
    },

    can_view_planning(userContext) {
        if (!userContext) return false;
        if (this.is_admin(userContext)) return true;
        return (userContext.roles || []).some((role) =>
            [...PLANNING_ROLES, ROLE_LIST.TEACHER].includes(role)
        );
    }
};
