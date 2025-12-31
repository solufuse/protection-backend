
# 🛡️ Solufuse Permissions & Roles Reference

This document outlines the access rules, quotas, and hierarchy implemented in the Backend (API v2.6+).

## 1. Global Hierarchy (SaaS)

| Global Role | Level | Description |
| :--- | :--- | :--- |
| **Guest** | 0 | Not logged in (Temporary session only). |
| **User** | 20 | Standard free user. |
| **Nitro** | 40 | Paid user (Storage benefits). |
| **Moderator** | 60 | Staff: Can view and moderate, but cannot destroy projects. |
| **Admin** | 80 | Staff: Full operational powers (except DB deletion). |
| **Super Admin**| 100 | Founder: Absolute powers (DB access, Logs). |

---

## 2. Storage Quotas

These limits are enforced during project creation or file uploads.

| Role | Max Projects (SQL) | Max Files (per folder/session) |
| :--- | :--- | :--- |
| **Guest** | 0 (Forbidden) | 10 |
| **User** | 1 | 100 |
| **Nitro** | 10 | 1000 |
| **Moderator+** | Unlimited | Unlimited |

---

## 3. Rights Matrix (Projects)

| Action | User / Nitro | Moderator | Admin | Super Admin |
| :--- | :--- | :--- | :--- | :--- |
| **Visibility** | Their projects only | **ALL** projects (Global View) | **ALL** projects | **ALL** projects |
| **Creation** | ✅ (If quota OK) | ✅ | ✅ | ✅ |
| **Deletion** | ✅ (If Owner) | ❌ **DENIED** | ✅ | ✅ |
| **Invitation** | ✅ (Their projects) | ✅ (In any project) | ✅ (Everywhere) | ✅ (Everywhere) |
| **Kicking** | ✅ (Their projects) | ✅ (Everywhere, except ranks > self) | ✅ (Everywhere) | ✅ (Everywhere) |

---

## 4. Critical Security Rules (Hardcoded)

### A. System File Protection
* **File `protection.db` (SQLite)**: 
    * ❌ **Admin / Moderator / User**: Cannot delete this file via `/files/delete`.
    * ✅ **Super Admin**: Authorized (Critical maintenance only).

### B. Anti-Coup (Hierarchy)
* A user can never modify the role of a hierarchical superior.
* A user cannot self-promote to a higher rank.
* A **Moderator** cannot kick an **Admin** or a Project **Owner**.

---
*Last updated: December 31, 2025*
