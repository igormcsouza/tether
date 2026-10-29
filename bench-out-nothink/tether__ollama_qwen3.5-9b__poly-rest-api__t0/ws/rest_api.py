import json
from collections import defaultdict


class RestAPI:
    def __init__(self, database):
        self.database = database

    def get(self, path, payload=None):
        if path == "/users":
            users = self._get_users()
            if payload is None:
                return {"users": users}
            else:
                user_names = json.loads(payload).get("users", [])
                filtered_users = [self._get_user(name) for name in user_names]
                return {"users": sorted(filtered_users, key=lambda u: u["name"])}
        return {}

    def post(self, path, payload):
        if path == "/add":
            user_name = json.loads(payload)["user"]
            return self._add_user(user_name)
        elif path == "/iou":
            data = json.loads(payload)
            lender = data["lender"]
            borrower = data["borrower"]
            amount = data["amount"]
            return self._create_iou(lender, borrower, amount)
        return {}

    def _get_users(self):
        return [self._get_user(u["name"]) for u in self.database["users"]]

    def _get_user(self, name):
        for u in self.database["users"]:
            if u["name"] == name:
                return u
        return None

    def _add_user(self, name):
        for u in self.database["users"]:
            if u["name"] == name:
                return u
        new_user = {
            "name": name,
            "owes": {},
            "owed_by": {},
            "balance": 0.0
        }
        self.database["users"].append(new_user)
        return new_user

    def _create_iou(self, lender, borrower, amount):
        lender_user = self._get_user(lender)
        borrower_user = self._get_user(borrower)
        
        if lender_user is None or borrower_user is None:
            return {"users": []}
        
        # Update lender's owes to borrower
        if borrower in lender_user["owes"]:
            lender_user["owes"][borrower] -= amount
            if lender_user["owes"][borrower] == 0:
                del lender_user["owes"][borrower]
        else:
            lender_user["owes"][borrower] = -amount
        
        # Update borrower's owed_by from lender
        if lender in borrower_user["owed_by"]:
            borrower_user["owed_by"][lender] -= amount
            if borrower_user["owed_by"][lender] == 0:
                del borrower_user["owed_by"][lender]
        else:
            borrower_user["owed_by"][lender] = -amount
        
        # Handle negative values (relationship flipped)
        if borrower in lender_user["owes"] and lender_user["owes"][borrower] < 0:
            # Adam owes Bob -1.0 means Adam is owed by Bob 1.0, so Bob owes Adam 1.0
            amount_to_move = abs(lender_user["owes"][borrower])
            del lender_user["owes"][borrower]
            if borrower_user["owes"].get(lender) is None:
                borrower_user["owes"][lender] = 0
            borrower_user["owes"][lender] += amount_to_move
        
        if lender in borrower_user["owed_by"] and borrower_user["owed_by"][lender] < 0:
            # Bob owes Adam -1.0 means Bob is owed by Adam 1.0, so Adam owes Bob 1.0
            amount_to_move = abs(borrower_user["owed_by"][lender])
            del borrower_user["owed_by"][lender]
            if lender_user["owes"].get(borrower) is None:
                lender_user["owes"][borrower] = 0
            lender_user["owes"][borrower] += amount_to_move
        
        # Recalculate balances
        self._recalculate_balance(lender_user)
        self._recalculate_balance(borrower_user)
        
        return {"users": sorted([lender_user, borrower_user], key=lambda u: u["name"])}

    def _recalculate_balance(self, user):
        total_owed_by = sum(user["owed_by"].values())
        total_owes = sum(user["owes"].values())
        user["balance"] = total_owed_by - total_owes


def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python rest_api.py <port>")
        sys.exit(1)
    
    port = int(sys.argv[1])
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = None
            if self.path == "/users":
                payload = self.rfile.read(1024).decode()
            api = RestAPI(database)
            response = api.get(self.path, payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        
        def do_POST(self):
            content_length = int(self.headers["Content-Length"])
            payload = self.rfile.read(content_length).decode()
            api = RestAPI(database)
            response = api.post(self.path, payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
    
    database = {"users": []}
    server = HTTPServer(("", port), RequestHandler)
    print(f"Server running on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    main()