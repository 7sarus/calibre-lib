#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Hardcover App GraphQL API Client.
Fetches user bookshelves, reading lists, and book identifiers (ISBN-10, ISBN-13, authors).
API Endpoint: https://api.hardcover.app/v1/graphql
"""

import json
import urllib.request
import urllib.error

HARDCOVER_GRAPHQL_ENDPOINT = "https://api.hardcover.app/v1/graphql"

# Standard Hardcover User Book Status IDs
STATUS_MAP = {
    1: "Want to Read",
    2: "Currently Reading",
    3: "Read",
    4: "Did Not Finish",
}


def _execute_graphql(query, variables=None, api_token=None, timeout=20):
    """Executes a GraphQL query against Hardcover API."""
    if not api_token or not api_token.strip():
        raise ValueError("Hardcover API token is required. Get one at https://hardcover.app/account/api")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Calibre-LibGen-Plugin/1.0",
        "Authorization": f"Bearer {api_token.strip()}",
    }

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        HARDCOVER_GRAPHQL_ENDPOINT,
        data=data_bytes,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
            if "errors" in result and result["errors"]:
                err_msg = result["errors"][0].get("message", "GraphQL query error")
                raise RuntimeError(f"Hardcover API error: {err_msg}")
            return result.get("data", {})
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"Hardcover HTTP {e.code}: {e.reason} ({body[:100]})")
    except Exception as e:
        raise RuntimeError(f"Hardcover request failed: {e}")


def fetch_user_shelves_and_lists(api_token, timeout=20):
    """
    Fetches the authenticated user's profile, default status counts, and custom lists.
    Returns:
        dict with:
            - 'username': str
            - 'shelves': list of dicts [{'type': 'shelf', 'id': 1, 'name': 'Want to Read'}, ...]
            - 'lists': list of dicts [{'type': 'list', 'id': 123, 'name': 'Favorites', 'books_count': 10}, ...]
    """
    query = """
    query GetUserLibrary {
      me {
        id
        username
        lists(order_by: {name: asc}) {
          id
          name
          books_count
        }
      }
    }
    """
    data = _execute_graphql(query, api_token=api_token, timeout=timeout)
    me_data = data.get("me", [])
    if not me_data:
        raise RuntimeError("No user account found for provided Hardcover API token.")

    me = me_data[0] if isinstance(me_data, list) else me_data
    username = me.get("username", "Unknown")

    shelves = [
        {"type": "status", "id": 1, "name": "Want to Read"},
        {"type": "status", "id": 2, "name": "Currently Reading"},
        {"type": "status", "id": 3, "name": "Read"},
        {"type": "status", "id": 4, "name": "Did Not Finish"},
    ]

    custom_lists = []
    for l in me.get("lists", []):
        custom_lists.append({
            "type": "list",
            "id": l.get("id"),
            "name": l.get("name", "Untitled List"),
            "books_count": l.get("books_count", 0),
        })

    return {
        "username": username,
        "shelves": shelves,
        "lists": custom_lists,
    }


def fetch_shelf_books(api_token, shelf_type="status", target_id=1, limit=100, timeout=25):
    """
    Fetches book records from a specific shelf status (Want to Read, Read, etc.) or custom list.
    Returns list of dicts:
        [{
            'title': str,
            'author': str,
            'isbn_10': str,
            'isbn_13': str,
            'best_isbn': str,
            'id': int,
            'release_year': str
        }, ...]
    """
    if shelf_type == "status":
        query = """
        query GetStatusBooks($status_id: Int!, $limit: Int!) {
          user_books(where: {status_id: {_eq: $status_id}}, limit: $limit, order_by: {id: desc}) {
            id
            book {
              id
              title
              release_year
              contributions {
                author {
                  name
                }
              }
              editions(limit: 5) {
                isbn_10
                isbn_13
              }
            }
          }
        }
        """
        variables = {"status_id": int(target_id), "limit": int(limit)}
        data = _execute_graphql(query, variables=variables, api_token=api_token, timeout=timeout)
        raw_items = data.get("user_books", [])
    else:
        # Custom list
        query = """
        query GetListBooks($list_id: Int!, $limit: Int!) {
          list_books(where: {list_id: {_eq: $list_id}}, limit: $limit, order_by: {position: asc}) {
            book {
              id
              title
              release_year
              contributions {
                author {
                  name
                }
              }
              editions(limit: 5) {
                isbn_10
                isbn_13
              }
            }
          }
        }
        """
        variables = {"list_id": int(target_id), "limit": int(limit)}
        data = _execute_graphql(query, variables=variables, api_token=api_token, timeout=timeout)
        raw_items = data.get("list_books", [])

    books = []
    for item in raw_items:
        b = item.get("book")
        if not b:
            continue

        title = b.get("title", "").strip()
        year = str(b.get("release_year") or "").strip()

        authors = []
        for c in b.get("contributions", []):
            auth = c.get("author", {}).get("name")
            if auth and auth.strip():
                authors.append(auth.strip())
        author_str = ", ".join(authors) if authors else "Unknown"

        isbn_10 = ""
        isbn_13 = ""
        for ed in b.get("editions", []):
            if not isbn_13 and ed.get("isbn_13"):
                isbn_13 = str(ed.get("isbn_13")).strip()
            if not isbn_10 and ed.get("isbn_10"):
                isbn_10 = str(ed.get("isbn_10")).strip()

        best_isbn = isbn_13 or isbn_10

        books.append({
            "title": title,
            "author": author_str,
            "isbn_10": isbn_10,
            "isbn_13": isbn_13,
            "best_isbn": best_isbn,
            "id": b.get("id"),
            "release_year": year,
        })

    return books
