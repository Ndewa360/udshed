# Copyright (c) 2026, Cédric Nguendap Bedjama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

STATUTS = [
	"Brouillon",
	"Candidatures ouvertes",
	"Épreuves",
	"Délibération",
	"Résultats publiés",
	"Clôturé",
]
# Une fois les résultats publiés, le concours ne peut plus revenir en arrière.
STATUTS_DEFINITIFS = ("Résultats publiés", "Clôturé")


def _cle_matiere(matiere):
	"""Deux saisies « Maths » et « maths  » désignent la même matière."""
	return " ".join((matiere or "").split()).casefold()


def concours_pour_formation(session_inscription, filiere, niveau):
	"""Concours (non clôturé) de la campagne qui recrute sur cette filière et ce
	niveau, sinon None : la formation est alors en admission sur dossier."""
	if not (session_inscription and filiere and niveau):
		return None
	parents = frappe.get_all(
		"Concours Filiere",
		filters={"parenttype": "Concours", "filiere": filiere, "niveau": niveau},
		pluck="parent",
	)
	if not parents:
		return None
	return frappe.db.get_value(
		"Concours",
		{
			"name": ["in", parents],
			"session_inscription": session_inscription,
			"statut": ["!=", "Clôturé"],
		},
		"name",
	)


class Concours(Document):
	def validate(self):
		self._verifier_campagne()
		self._verifier_dates()
		self._verifier_note(self.moyenne_minimale, _("La moyenne minimale du concours"))
		self._verifier_filieres()
		self._verifier_epreuves()
		self._verifier_statut()
		if self.statut != "Brouillon":
			self._verifier_configuration_complete()

	# ------------------------------------------------------------ contrôles
	def _verifier_campagne(self):
		annee = frappe.db.get_value("Session Inscription", self.session_inscription, "academic_year")
		if annee and annee != self.academic_year:
			frappe.throw(
				_("La campagne {0} appartient à l'année {1}, pas à l'année {2}.").format(
					self.session_inscription, annee, self.academic_year
				)
			)

	def _verifier_dates(self):
		if self.date_debut_epreuves and self.date_fin_epreuves and self.date_fin_epreuves < self.date_debut_epreuves:
			frappe.throw(_("La fin des épreuves doit être après leur début."))
		if (
			self.date_publication_resultats
			and self.date_fin_epreuves
			and self.date_publication_resultats < self.date_fin_epreuves
		):
			frappe.throw(_("Les résultats ne peuvent pas être publiés avant la fin des épreuves."))

	@staticmethod
	def _verifier_note(valeur, libelle):
		if valeur is not None and valeur != "" and not (0 <= float(valeur) <= 20):
			frappe.throw(_("{0} doit être comprise entre 0 et 20.").format(libelle))

	def _verifier_filieres(self):
		vues = set()
		for row in self.filieres:
			cle = (row.filiere, row.niveau)
			if cle in vues:
				frappe.throw(
					_("Ligne {0} : la filière {1} niveau {2} est déjà dans le tableau.").format(
						row.idx, row.filiere, row.niveau
					)
				)
			vues.add(cle)
			parent = frappe.db.get_value("Field of study Level", row.niveau, "parent")
			if parent and parent != row.filiere:
				frappe.throw(
					_("Ligne {0} : le niveau {1} n'appartient pas à la filière {2}.").format(
						row.idx, row.niveau, row.filiere
					)
				)
			if (row.places or 0) < 1:
				frappe.throw(_("Ligne {0} : indiquez au moins une place pour {1}.").format(row.idx, row.filiere))
			self._verifier_note(
				row.moyenne_minimale,
				_("Ligne {0} : la moyenne minimale de {1}").format(row.idx, row.filiere),
			)
			self._verifier_formation_libre(row)

	def _verifier_formation_libre(self, row):
		"""Une même formation ne peut recruter que par un seul concours actif d'une campagne."""
		if self.statut == "Clôturé":
			return
		autre = concours_pour_formation(self.session_inscription, row.filiere, row.niveau)
		if autre and autre != self.name:
			frappe.throw(
				_("Ligne {0} : {1} niveau {2} est déjà au programme du concours {3}.").format(
					row.idx, row.filiere, row.niveau, autre
				)
			)

	def _verifier_epreuves(self):
		filieres = {row.filiere for row in self.filieres}
		communes, par_filiere = set(), set()
		for row in self.epreuves:
			if row.filiere and row.filiere not in filieres:
				frappe.throw(
					_("Épreuve ligne {0} : la filière {1} n'est pas dans le tableau des filières.").format(
						row.idx, row.filiere
					)
				)
			if (row.coefficient or 0) <= 0:
				frappe.throw(_("Épreuve ligne {0} : le coefficient doit être supérieur à 0.").format(row.idx))
			self._verifier_note(
				row.note_eliminatoire,
				_("Épreuve ligne {0} : la note éliminatoire").format(row.idx),
			)
			cle = _cle_matiere(row.matiere)
			if (row.filiere and (cle, row.filiere) in par_filiere) or (not row.filiere and cle in communes):
				frappe.throw(_("Épreuve ligne {0} : « {1} » est déjà prévue.").format(row.idx, row.matiere))
			if row.filiere:
				par_filiere.add((cle, row.filiere))
			else:
				communes.add(cle)
		conflit = {cle for cle, _f in par_filiere} & communes
		if conflit:
			matiere = next(r.matiere for r in self.epreuves if _cle_matiere(r.matiere) in conflit)
			frappe.throw(
				_("« {0} » est à la fois commune à toutes les filières et propre à une filière. "
				  "Gardez une seule des deux formes.").format(matiere)
			)

	def _verifier_statut(self):
		avant = self.get_doc_before_save()
		if not avant or avant.statut == self.statut:
			return
		# La délibération porte sur des notes nominatives : l'anonymat doit être levé.
		if (
			STATUTS.index(self.statut) >= STATUTS.index("Délibération")
			and STATUTS.index(avant.statut) < STATUTS.index("Délibération")
			and not self.anonymat_leve
		):
			frappe.throw(
				_("Validez toutes les notes puis utilisez « Lever l'anonymat » : "
				  "le concours passera alors automatiquement en « Délibération ».")
			)
		# Sans candidat autorisé, il n'y a aucune copie à corriger.
		if self.statut == "Épreuves" and STATUTS.index(avant.statut) < STATUTS.index("Épreuves") \
				and not frappe.db.count("Candidat Concours", {"concours": self.name}):
			frappe.throw(
				_("Aucun candidat n'est autorisé à concourir : passez d'abord des candidatures au statut "
				  "« Autorisé à concourir » (elles doivent demander une formation du concours et appartenir "
				  "à la session d'inscription {0}).").format(self.session_inscription)
			)
		if avant.statut in STATUTS_DEFINITIFS and STATUTS.index(self.statut) < STATUTS.index(avant.statut):
			frappe.throw(
				_("Le concours est au statut « {0} » : il ne peut plus revenir à « {1} ».").format(
					avant.statut, self.statut
				)
			)

	def _verifier_configuration_complete(self):
		if not self.filieres:
			frappe.throw(_("Ajoutez au moins une filière avant de quitter le statut Brouillon."))
		sans_epreuve = [row.filiere for row in self.filieres if not self.epreuves_de_filiere(row.filiere)]
		if sans_epreuve:
			frappe.throw(
				_("Aucune épreuve n'est prévue pour : {0}. Ajoutez une épreuve propre ou commune.").format(
					", ".join(sorted(set(sans_epreuve)))
				)
			)

	# ------------------------------------------------------------ utilitaires
	def epreuves_de_filiere(self, filiere):
		"""Épreuves composées par un candidat de cette filière : communes + propres."""
		return [row for row in self.epreuves if not row.filiere or row.filiere == filiere]

	def moyenne_minimale_de(self, filiere, niveau):
		for row in self.filieres:
			# Un champ Float vide vaut 0 : 0 signifie donc « moyenne du concours ».
			if row.filiere == filiere and row.niveau == niveau and row.moyenne_minimale:
				return float(row.moyenne_minimale)
		return float(self.moyenne_minimale or 0)
