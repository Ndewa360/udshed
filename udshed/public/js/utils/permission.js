window.Udshed = window.Udshed || {};

const ROLE_LIST = {
    ADMINISTRATOR: "Administrator",
    SYSTEM_MANAGER: "System Manager",
    COORDINATOR: "Coordonateur",
    PLANNING_MANAGER: "Planning Manager",
    PLANNING_ADMIN: "Planning Admin",
    TEACHER: "Teacher",
    ENSEIGNANT: "Enseignant",
    STUDENT: "Student"
};

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
                .flatMap((row) => row[key].map((item) => item && (item.name || item) ))
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
        return roles.includes(ROLE_LIST.ADMINISTRATOR) || roles.includes(ROLE_LIST.SYSTEM_MANAGER);
    },

    should_apply_filter(userContext) {
        return !this.is_admin(userContext);
    },

    user_can_edit_planning_cell(cellFilter, userContext) {
        if (!userContext) return false;
        if (this.is_admin(userContext)) return true;
        const editableRoles = [ROLE_LIST.COORDINATOR, ROLE_LIST.PLANNING_MANAGER];
        const hasRole = (userContext.roles || []).some((role) => editableRoles.includes(role));
        if (!hasRole) return false;
        const perms = (userContext.perms || []).filter((perm) => {
            if (!perm.academic_year_list || !perm.filiere || !perm.niveau) return false;
            const acadFound = perm.academic_year_list.find((acad) => (acad.name || acad) === cellFilter.academic_year);
            const filiereFound = perm.filiere.find((fil) => (fil.name || fil) === cellFilter.filiere);
            const niveauFound = perm.niveau.find((niv) => (niv.name || niv) === cellFilter.niveau);
            return acadFound && filiereFound && niveauFound;
        });
        return perms.some((perm) => editableRoles.includes(perm.role));
    },

    can_view_planning(userContext) {
        if (!userContext) return false;
        if (this.is_admin(userContext)) return true;
        return (userContext.roles || []).some((role) =>
            [ROLE_LIST.COORDINATOR, ROLE_LIST.PLANNING_MANAGER, ROLE_LIST.TEACHER, ROLE_LIST.ENSEIGNANT].includes(role)
        );
    }
};
