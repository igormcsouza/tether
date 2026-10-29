import json


class RestAPI:
    def __init__(self, database=None):
        if database is None:
            database = {"users": []}
        self.database = database

    def get(self, url, payload=None):
        if url == "/users":
            if payload is None:
                # Return all users
                users = self.database["users"]
                return json.dumps({"users": users})
            else:
                # Filter users by names in payload
                user_names = json.loads(payload)["users"]
                filtered_users = [
                    user for user in self.database["users"]
                    if user["name"] in user_names
                ]
                # Sort by name
                filtered_users.sort(key=lambda x: x["name"])
                return json.dumps({"users": filtered_users})
        return json.dumps({})

    def post(self, url, payload=None):
        if url == "/add":
            if payload is None:
                return json.dumps({})
            else:
                data = json.loads(payload)
                user_name = data["user"]
                
                # Check if user already exists
                for user in self.database["users"]:
                    if user["name"] == user_name:
                        return json.dumps(user)
                
                # Create new user
                new_user = {
                    "name": user_name,
                    "owes": {},
                    "owed_by": {},
                    "balance": 0.0
                }
                
                # Add to database
                self.database["users"].append(new_user)
                
                return json.dumps(new_user)
        
        elif url == "/iou":
            if payload is None:
                return json.dumps({})
            else:
                data = json.loads(payload)
                lender = data["lender"]
                borrower = data["borrower"]
                amount = data["amount"]
                
                # Find lender and borrower in database
                lender_user = None
                borrower_user = None
                
                for user in self.database["users"]:
                    if user["name"] == lender:
                        lender_user = user
                    if user["name"] == borrower:
                        borrower_user = user
                
                # If either user doesn't exist, create them
                if lender_user is None:
                    lender_user = {
                        "name": lender,
                        "owes": {},
                        "owed_by": {},
                        "balance": 0.0
                    }
                    self.database["users"].append(lender_user)
                
                if borrower_user is None:
                    borrower_user = {
                        "name": borrower,
                        "owes": {},
                        "owed_by": {},
                        "balance": 0.0
                    }
                    self.database["users"].append(borrower_user)
                
                # If lender already owes borrower, reduce that debt
                if borrower in lender_user["owes"]:
                    lender_user["owes"][borrower] -= amount
                    # If debt becomes 0, remove the entry
                    if lender_user["owes"][borrower] == 0:
                        del lender_user["owes"][borrower]
                
                # If borrower already owes lender, reduce that debt
                if lender in borrower_user["owed_by"]:
                    borrower_user["owed_by"][lender] -= amount
                    # If debt becomes 0, remove the entry
                    if borrower_user["owed_by"][lender] == 0:
                        del borrower_user["owed_by"][lender]
                
                # Update lender: they are owed by borrower (owed_by[borrower] increases)
                if borrower in lender_user["owed_by"]:
                    lender_user["owed_by"][borrower] += amount
                else:
                    lender_user["owed_by"][borrower] = amount
                
                # Update borrower: they owe lender (owes[lender] increases)
                if lender in borrower_user["owes"]:
                    borrower_user["owes"][lender] += amount
                else:
                    borrower_user["owes"][lender] = amount
                
                # Calculate balances
                lender_user["balance"] = sum(lender_user["owed_by"].values()) - sum(lender_user["owes"].values())
                borrower_user["balance"] = sum(borrower_user["owed_by"].values()) - sum(borrower_user["owes"].values())
                
                # Return updated users sorted by name
                result_users = []
                for user in self.database["users"]:
                    if user["name"] == lender or user["name"] == borrower:
                        result_users.append(user)
                
                result_users.sort(key=lambda x: x["name"])
                
                return json.dumps({"users": result_users})
        
        return json.dumps({})