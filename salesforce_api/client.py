from __future__ import unicode_literals

import json
import os

from six import integer_types, iteritems, string_types

import frappe
import frappe.model
import frappe.utils
from frappe import _
from frappe.desk.reportview import validate_args
from frappe.model.db_query import check_parent_permission
from frappe.utils import get_safe_filters


# Define a function to wrap response data in case of exceptions
def wrap_response_data(data, response_code=200, exception=None, traceback=None):
    response = {
        "data": data,
        "response_code": response_code,
        "exception": str(exception) if exception else None,
        "traceback": traceback,
    }
    return response

@frappe.whitelist()
def get_list(
	doctype,
	fields=None,
	filters=None,
	order_by=None,
	limit_start=None,
	limit_page_length=20,
	parent=None,
	debug=False,
	as_dict=True,
	or_filters=None,
):
    try:
        if frappe.is_table(doctype):
            check_parent_permission(parent, doctype)

        args = frappe._dict(
            doctype=doctype,
            fields=fields,
            filters=filters,
            or_filters=or_filters,
            order_by=order_by,
            limit_start=limit_start,
            limit_page_length=limit_page_length,
            debug=debug,
            as_list=not as_dict,
        )

        validate_args(args)
        return frappe.get_list(**args)

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist()
def get_count(doctype, filters=None, debug=False, cache=False):
    try:
        return wrap_response_data(frappe.db.count(doctype, get_safe_filters(filters), debug, cache))

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist()
def get(doctype, name=None, filters=None, parent=None):
    try:
        if frappe.is_table(doctype):
            check_parent_permission(parent, doctype)

        if filters and not name:
            name = frappe.db.get_value(doctype, json.loads(filters))
            if not name:
                frappe.throw(_("No document found for given filters"))

        doc = frappe.get_doc(doctype, name)
        if not doc.has_permission("read"):
            raise frappe.PermissionError

        return doc.as_dict()

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist()
def get_value(doctype, fieldname, filters=None, as_dict=True, debug=False, parent=None):
    try:
        if frappe.is_table(doctype):
            check_parent_permission(parent, doctype)

        if not frappe.has_permission(doctype):
            frappe.throw(_("No permission for {0}").format(_(doctype)), frappe.PermissionError)

        filters = get_safe_filters(filters)
        if isinstance(filters, string_types):
            filters = {"name": filters}

        try:
            fields = frappe.parse_json(fieldname)
        except (TypeError, ValueError):
            # name passed, not json
            fields = [fieldname]

        if not filters:
            filters = None

        if frappe.get_meta(doctype).issingle:
            value = frappe.db.get_values_from_single(fields, filters, doctype, as_dict=as_dict, debug=debug)
        else:
            value = get_list(
                doctype,
                filters=filters,
                fields=fields,
                debug=debug,
                limit_page_length=1,
                parent=parent,
                as_dict=as_dict,
            )

        if as_dict:
            return wrap_response_data(value[0] if value else {})

        if not value:
            return

        return value[0] if len(fields) > 1 else value[0][0]

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist()
def get_single_value(doctype, field):
    try:
        if not frappe.has_permission(doctype):
            frappe.throw(_("No permission for {0}").format(_(doctype)), frappe.PermissionError)
        value = frappe.db.get_single_value(doctype, field)
        return value

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist(methods=["POST", "PUT"])
def set_value(doctype, name, fieldname, value=None):
    try:
        if fieldname != "idx" and fieldname in frappe.model.default_fields:
            frappe.throw(_("Cannot edit standard fields"))

        if not value:
            values = fieldname
            if isinstance(fieldname, string_types):
                try:
                    values = json.loads(fieldname)
                except ValueError:
                    values = {fieldname: ""}
        else:
            values = {fieldname: value}

        doc = frappe.db.get_value(doctype, name, ["parenttype", "parent"], as_dict=True)
        if doc and doc.parent and doc.parenttype:
            doc = frappe.get_doc(doc.parenttype, doc.parent)
            child = doc.getone({"doctype": doctype, "name": name})
            child.update(values)
        else:
            doc = frappe.get_doc(doctype, name)
            doc.update(values)

        doc.save()

        return doc.as_dict()

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist(methods=["POST", "PUT"])
def insert(doc=None):
    try:
        if isinstance(doc, string_types):
            doc = json.loads(doc)

        if doc.get("parent") and doc.get("parenttype"):
            # inserting a child record
            parent = frappe.get_doc(doc.get("parenttype"), doc.get("parent"))
            parent.append(doc.get("parentfield"), doc)
            parent.save()
            return wrap_response_data(parent.as_dict())
        else:
            doc = frappe.get_doc(doc).insert()
            return doc.as_dict()

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist(methods=["POST", "PUT"])
def insert_many(docs=None):
    try:
        if isinstance(docs, string_types):
            docs = json.loads(docs)

        out = []

        if len(docs) > 200:
            frappe.throw(_("Only 200 inserts allowed in one request"))

        for doc in docs:
            if doc.get("parent") and doc.get("parenttype"):
                # inserting a child record
                parent = frappe.get_doc(doc.get("parenttype"), doc.get("parent"))
                parent.append(doc.get("parentfield"), doc)
                parent.save()
                out.append(parent.name)
            else:
                doc = frappe.get_doc(doc).insert()
                out.append(doc.name)

        return out

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist(methods=["POST", "PUT"])
def save(doc):
    try:
        if isinstance(doc, string_types):
            doc = json.loads(doc)

        doc = frappe.get_doc(doc)
        doc.save()

        return doc.as_dict()

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist(methods=["POST", "PUT"])
def rename_doc(doctype, old_name, new_name, merge=False):
    try:
        new_name = frappe.rename_doc(doctype, old_name, new_name, merge=merge)
        return new_name

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist(methods=["POST", "PUT"])
def submit(doc):
    try:
        if isinstance(doc, string_types):
            doc = json.loads(doc)

        doc = frappe.get_doc(doc)
        doc.submit()

        return doc.as_dict()

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist(methods=["POST", "PUT"])
def cancel(doctype, name):
    try:
        wrapper = frappe.get_doc(doctype, name)
        wrapper.cancel()

        return wrapper.as_dict()

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

@frappe.whitelist(methods=["DELETE", "POST"])
def delete(doctype, name):
    try:
        frappe.delete_doc(doctype, name, ignore_missing=False)

        return None

    except Exception as e:
        return wrap_response_data(None, response_code=500, exception=e, traceback=frappe.get_traceback())

