
# 🛡️ Solufuse Permissions & Roles Reference

Ce document recense les règles d'accès, les quotas et la hiérarchie implémentés dans le Backend (API v2.6+).

## 1. Hiérarchie Globale (SaaS)

| Rôle Global | Level | Description |
| :--- | :--- | :--- |
| **Guest** | 0 | Visiteur non connecté (Session temporaire uniquement). |
| **User** | 20 | Utilisateur gratuit standard. |
| **Nitro** | 40 | Utilisateur payant (Avantages stockage). |
| **Moderator** | 60 | Staff : Peut voir et modérer, mais pas détruire. |
| **Admin** | 80 | Staff : Pleins pouvoirs opérationnels (sauf DB). |
| **Super Admin**| 100 | Fondateur : Pouvoirs absolus (accès DB, Logs). |

---

## 2. Quotas de Stockage

Ces limites sont appliquées lors de la création de projets ou l'upload de fichiers.

| Rôle | Max Projets (SQL) | Max Fichiers (par dossier/session) |
| :--- | :--- | :--- |
| **Guest** | 0 (Interdit) | 10 |
| **User** | 1 | 100 |
| **Nitro** | 10 | 1000 |
| **Moderator+** | Illimité | Illimité |

---

## 3. Matrice des Droits (Projets)

| Action | User / Nitro | Moderator | Admin | Super Admin |
| :--- | :--- | :--- | :--- | :--- |
| **Visibilité** | Ses projets uniquement | **TOUS** les projets (Vue Globale) | **TOUS** les projets | **TOUS** les projets |
| **Création** | ✅ (Si quota OK) | ✅ | ✅ | ✅ |
| **Suppression** | ✅ (Si Owner) | ❌ **REFUSÉ** | ✅ | ✅ |
| **Invitation** | ✅ (Ses projets) | ✅ (Dans n'importe quel projet) | ✅ (Partout) | ✅ (Partout) |
| **Expulsion** | ✅ (Ses projets) | ✅ (Partout, sauf grades > soi) | ✅ (Partout) | ✅ (Partout) |

---

## 4. Règles de Sécurité Critiques (Hardcoded)

### A. Protection des Fichiers Système
* **Fichier `protection.db` (SQLite)** : 
    * ❌ **Admin / Moderator / User** : Impossible de supprimer ce fichier via `/files/delete`.
    * ✅ **Super Admin** : Autorisé (Maintenance critique uniquement).

### B. Anti-Putsch (Hiérarchie)
* Un utilisateur ne peut jamais modifier le rôle d'un supérieur hiérarchique.
* Un utilisateur ne peut pas s'auto-promouvoir à un grade supérieur.
* Un **Moderator** ne peut pas expulser (Kick) un **Admin** ou un **Owner** de projet.

---
*Dernière mise à jour : 31 Décembre 2025*
