
# 🛡️ Solufuse Permissions & Roles Reference

This document outlines the access rules, quotas, and hierarchy implemented in the Backend (API v2.6+).

---

## 1. Global Hierarchy (SaaS Level)
*Controls access to the platform features and storage quotas.*

| Global Role | Level | Description |
| :--- | :--- | :--- |
| **Guest** | 0 | Not logged in (Temporary session only). |
| **User** | 20 | Standard free user. |
| **Nitro** | 40 | Paid user (Storage benefits). |
| **Moderator** | 60 | Staff: Can view all projects globally. Cannot delete. |
| **Admin** | 80 | Staff: Full operational powers (except DB deletion). |
| **Super Admin**| 100 | Founder: Absolute powers (DB access, Logs). |

### Storage Quotas
| Role | Max Projets | Max Fichiers (par dossier) |
| :--- | :--- | :--- |
| **Guest** | 0 | 10 |
| **User** | 1 | 100 |
| **Nitro** | 10 | 1000 |
| **Moderator+** | ∞ | ∞ |

---

## 2. Project Hierarchy (Team Level)
*Controls access within a specific project. Assigned by the Project Owner or Admins.*

| Project Role | Level | Description |
| :--- | :--- | :--- |
| **Viewer** | 10 | **Read-Only**: Can download files. Cannot upload or delete. |
| **Editor** | 20 | **Read/Write**: Can upload and delete files. Cannot manage members. |
| **Moderator** | 30 | **Team Lead**: Can invite/kick Viewers & Editors. |
| **Admin** | 40 | **Manager**: Can invite/kick anyone (except Owner). Can change roles. |
| **Owner** | 50 | **Creator**: Absolute control. Can delete the project. |

### Note on Global Staff Override
* **Global Super Admin / Admin / Moderator** automatically bypass project restrictions.
* They are treated as **Level 100** inside any project, allowing them to moderate content without needing an explicit invite.

---

## 3. Interaction Rules (The "Anti-Coup" Logic)

To ensure stability and prevent privilege escalation, the following strict mathematical rules apply to all invites and kicks:

### A. Invitation / Promotion Rule
> **Rule:** You cannot assign a role **greater than or equal to** your own.

* ❌ A Project **Admin (40)** cannot promote someone to **Admin (40)**.
* ❌ A Project **Moderator (30)** cannot promote someone to **Admin (40)**.
* ✅ A Project **Admin (40)** CAN promote someone to **Moderator (30)**.
* ✅ The **Owner (50)** CAN promote someone to **Admin (40)**.

### B. Kick / Demotion Rule
> **Rule:** You cannot kick or modify a member with a rank **greater than or equal to** your own.

* ❌ A Project **Admin** cannot kick another **Admin**.
* ❌ No one can kick the **Owner**.
* ✅ An **Admin** CAN kick a **Moderator**, **Editor**, or **Viewer**.

---

## 4. Critical Security (Files)

* **File `protection.db`**: 
    * ❌ **Admin / Moderator / User**: Cannot delete this file.
    * ✅ **Super Admin**: Authorized (Critical maintenance only).

---
*Last updated: December 31, 2025*
