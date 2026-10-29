import json


class RestAPI:
    def __init__(self, database=None):
        if database is None:
            database = {"users": []}
        self.database = database

    def _get_user(self, name):
        for user in self.database["users"]:
            if user["name"] == name:
                return user
        return {
            "name": name,
            "owes": {},
            "owed_by": {},
            "balance": 0.0
        }

    def _update_user(self, user):
        for i, u in enumerate(self.database["users"]):
            if u["name"] == user["name"]:
                self.database["users"][i] = user
                return True
        return False

    def _calculate_balance(self, user):
        total_owed_by = sum(user["owed_by"].values())
        total_owed = sum(user["owes"].values())
        return total_owed_by - total_owed

    def get(self, url, payload=None):
        if url == "/users":
            if payload is None:
                users = self.database["users"]
                users = sorted(users, key=lambda u: u["name"])
                return json.dumps({"users": users})
            else:
                user_names = json.loads(payload)["users"]
                users = [u for u in self.database["users"] if u["name"] in user_names]
                users = sorted(users, key=lambda u: u["name"])
                return json.dumps({"users": users})
        return json.dumps({})

    def post(self, url, payload=None):
        if url == "/add":
            if payload is None:
                return json.dumps({})
            else:
                data = json.loads(payload)
                user_name = data["user"]
                user = self._get_user(user_name)
                self._update_user(user)
                return json.dumps(user)

        elif url == "/iou":
            if payload is None:
                return json.dumps({})
            else:
                data = json.loads(payload)
                lender = data["lender"]
                borrower = data["borrower"]
                amount = data["amount"]

                lender_user = self._get_user(lender)
                borrower_user = self._get_user(borrower)

                # If lender already owes borrower, reduce that debt
                if borrower in lender_user["owes"]:
                    existing_debt = lender_user["owes"][borrower]
                    if amount >= existing_debt:
                        # New loan cancels or exceeds old debt
                        # Lender no longer owes borrower, and is now owed by borrower
                        del lender_user["owes"][borrower]
                        # Lender is now owed by borrower for (amount - existing_debt)
                        if lender in borrower_user["owed_by"]:
                            borrower_user["owed_by"][lender] += amount - existing_debt
                        else:
                            borrower_user["owed_by"][lender] = amount - existing_debt
                    else:
                        # Partial reduction - lender still owes borrower, but less
                        lender_user["owes"][borrower] -= amount
                        if lender_user["owes"][borrower] == 0:
                            del lender_user["owes"][borrower]
                        # Lender is now owed by borrower for the new loan amount
                        if lender in borrower_user["owed_by"]:
                            borrower_user["owed_by"][lender] += amount
                        else:
                            borrower_user["owed_by"][lender] = amount
                else:
                    # Lender doesn't owe borrower, so lender is now owed by borrower
                    if lender in borrower_user["owes"]:
                        borrower_user["owes"][lender] += amount
                    else:
                        borrower_user["owes"][lender] = amount
                    if borrower in lender_user["owed_by"]:
                        lender_user["owed_by"][borrower] += amount
                    else:
                        lender_user["owed_by"][borrower] = amount

                lender_user["balance"] = self._calculate_balance(lender_user)
                borrower_user["balance"] = self._calculate_balance(borrower_user)

                self._update_user(lender_user)
                self._update_user(borrower_user)

                users = [lender_user, borrower_user]
                users = sorted(users, key=lambda u: u["name"])
                return json.dumps({"users": users})

        return json.dumps({})