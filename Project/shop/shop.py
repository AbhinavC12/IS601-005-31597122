import traceback
from flask import Blueprint, request, flash, render_template, redirect, url_for
from werkzeug.datastructures import MultiDict
from shop.forms import ItemForm
from sql.db import DB
from roles.permissions import admin_permission
from flask_login import login_required, current_user
shop = Blueprint('shop', __name__, url_prefix='/',template_folder='templates')

@shop.route("/admin/item", methods=["GET","POST"])
@admin_permission.require(http_exception=403)
def item():
    form = ItemForm()
    id = request.args.get("id", form.id.data or None)
    type = "Edit" if id else "Create"
    if form.validate_on_submit():
        if form.id.data: # it's an update
            try:
                result = DB.update("UPDATE IS601_S_Products set name = %s, description = %s, category = %s, stock = %s, unit_price = %s, visibility=%s WHERE id = %s",
                form.name.data, form.description.data, form.category.data, form.stock.data, form.unit_price.data, 1 if form.visibility.data else 0, form .id.data)
                if result.status:
                    flash(f"Updated {form.name.data}", "success")
            except Exception as e:
                print("Error updating item", e)
                flash(f"Error updating item {form.name.data}", "danger")
        else: # it's a create
            try:
                result = DB.update("""INSERT INTO IS601_S_Products (name, description, category, stock, unit_price, visibility) 
                VALUES (%s,%s,%s,%s,%s, %s)""",
                form.name.data, form.description.data, form.category.data, form.stock.data, form.unit_price.data, 1 if form.visibility.data else 0)
                if result.status:
                    flash(f"Created {form.name.data}", "success")
                    form = ItemForm() # clear form
            except Exception as e:
                print("Error creating item", e)
                flash(f"Error creating item {form.name.data}", "danger")
    if id:
        try:
            result = DB.selectOne("SELECT id, name, description, category, stock, unit_price, visibility FROM IS601_S_Products WHERE id = %s", id)
            if result.status and result.row:
                    form.process(MultiDict(result.row))
        except Exception as e:
            print("Error fetching item", e)
            flash("Item not found", "danger")
    return render_template("item.html", form=form, type=type)

@shop.route("/admin/items/delete", methods=["GET"])
@admin_permission.require(http_exception=403)
def delete():
    id = request.args.get("id")
    if id:
        try:
            result = DB.delete("DELETE FROM IS601_S_Items WHERE id = %s", id)
            if result.status:
                flash("Deleted item", "success")
        except Exception as e:
            print("Error deleting item",e)
            flash("Error deleting item", "danger")
    return redirect(url_for("shop.items"))

@shop.route("/admin/items", methods=["GET","POST"])
@admin_permission.require(http_exception=403)
def items():
    rows = []
    try:
        result = DB.selectAll("SELECT id, name, description, stock, unit_price, visibility FROM IS601_S_Products LIMIT 25",)
        if result.status and result.rows:
            rows = result.rows
    except Exception as e:
        print("Error fetching items", e)
        flash("There was a problem loading items", "danger")
    return render_template("items.html", rows=rows)

@shop.route("/shop", methods=["GET","POST"])
def shop_list():
    rows = []
    args = []
    ##UCID: ac2526 Date Dec 17th
    name = request.args.get("name")
    category = request.args.get("category")
    price = request.args.get("price")
    query = "SELECT id, name, description, stock, unit_price FROM IS601_S_Products WHERE stock > 0 AND visibility = 1"
    if name:
        query += " AND name LIKE %s"
        args.append(f"%{name}%")
    if category:
        query += f" AND category = '{category}'"
    if price:
        query += f" ORDER BY unit_price {price}"
    query += " LIMIT 10"
    try:
        result = DB.selectAll(query, *args)
        if result.status and result.rows:
            rows = result.rows
    except Exception as e:
        print("Error fetching items", e)
        flash("There was a problem loading items", "danger")
    return render_template("shop.html", rows=rows)

@shop.route("/cart", methods=["GET","POST"])
def cart():
    if not current_user.is_authenticated:
        flash("Please login to add the cart", "warning")
        return redirect(url_for('shop.shop_list'))
    delete_all =  request.args.get('delete_all')
    item_id = request.form.get("item_id")
    id = request.form.get("id", item_id)
    print("id", id)
    quantity = request.form.get("quantity", 1, type=int)
    user_id = current_user.get_id()
    if id and user_id:
        if quantity > 0:
            try:
                result = DB.selectOne("SELECT unit_price,name from IS601_S_Products WHERE id = %s", id)
                print("result", result)
                if result.status and result.row:
                    cost = result.row["unit_price"]
                    name = result.row["name"]
                    if item_id: # update from cart
                        result = DB.insertOne("""
                        UPDATE IS601_S_Cart SET
                        desired_quantity = %(quantity)s,
                        unit_price = %(cost)s
                        WHERE product_id = %(id)s and user_id = %(user_id)s
                        """,{
                            "id":id,
                            "quantity": quantity,
                            "cost":cost,
                            "user_id":user_id
                        })
                        if result.status:
                            flash(f"Updated quantity for {name} to {quantity}", "success")
                    else: #add from shop
                        result = DB.insertOne("""
                        INSERT INTO IS601_S_Cart (product_id, desired_quantity, unit_price, user_id)
                        VALUES(%(id)s, %(quantity)s, %(cost)s, %(user_id)s)
                        ON DUPLICATE KEY UPDATE
                        desired_quantity = desired_quantity + %(quantity)s,
                        unit_price = %(cost)s
                        """,{
                            "id":id,
                            "quantity": quantity,
                            "cost":cost,
                            "user_id":user_id
                        })
                        if result.status:
                            flash(f"Added {quantity} of {name} to cart", "success")
            except Exception as e:
                print("Error updating cart" ,e)
                flash("Error updating cart", "danger")
        else:
            # assuming delete
            try:
                result = DB.delete("DELETE FROM IS601_S_Cart where product_id = %s and user_id = %s", id, user_id)
                if result.status:
                    flash("Deleted item from cart", "success")
            except Exception as e:
                print("Error deleting item", e)
                flash("Error deleting item from cart", "danger")
    if delete_all:
        result = DB.delete("DELETE FROM IS601_S_Cart WHERE user_id = %s", user_id)
        if result.status:
            flash("Cleared cart", "success")
    rows = []
    try:
        result = DB.selectAll("""SELECT c.id, c.product_id, name, c.desired_quantity, (c.desired_quantity * c.unit_price) as subtotal 
        FROM IS601_S_Cart c JOIN IS601_S_Products i on c.product_id = i.id
        WHERE c.user_id = %s
        """, current_user.get_id())
        if result and result.rows:
            rows = result.rows
    except Exception as e:
        print("Error getting cart", e)
        flash("Error fetching cart", "danger")
    return render_template("cart.html", rows=rows)

@shop.route("/purchase", methods=["GET","POST"])
@login_required
def purchase():
    cart = []
    total = 0
    quantity = 0
    order = {}
    try:
        DB.getDB().autocommit = False # make a transaction

        # get cart to verify
        
        result = DB.selectAll("""SELECT c.id, item_id, name, c.quantity, i.stock, c.cost as cart_cost, i.cost as item_cost, (c.quantity * c.cost) as subtotal 
        FROM IS601_S_Cart c JOIN IS601_S_Items i on c.item_id = i.id
        WHERE c.user_id = %s
        """, current_user.get_id())
        if result.status and result.rows:
            cart = result.rows
        # verify cart
        has_error = False
        for item in cart:
            if item["quantity"] > item["stock"]:
                flash(f"Item {item['name']} doesn't have enough stock left", "warning")
                has_error = True
            if item["cart_cost"] != item["item_cost"]:
                flash(f"Item {item['name']}'s price has changed, please refresh cart", "warning")
                has_error = True
            total += int(item["subtotal"] or 0)
            quantity += int(item["quantity"])
        # check can afford
        if not has_error:
            balance = int(current_user.get_balance())
            if total > balance:
                flash("You can't afford to make this purchase", "danger")
                has_error = True
        # create order data
        order_id = -1
        if not has_error:
            result = DB.insertOne("""INSERT INTO IS601_S_Orders (total_spent, number_of_items, user_id)
            VALUES (%s, %s, %s)""", total, quantity, current_user.get_id())
            if not result.status:
                flash("Error generating order", "danger")
                DB.getDB().rollback()
                has_error = True
            else:
                order_id = int(DB.db.fetch_eof_status()["insert_id"])
                order["order_id"] = order_id
                order["total"] = total
                order["quantity"] = quantity
        # record order history
        if order_id > -1 and not has_error:
            # Note: Not really an insert 1, it'll copy data from Table B into Table A
            result = DB.insertOne("""INSERT INTO IS601_S_OrderItems (quantity, cost, order_id, item_id, user_id)
            SELECT quantity, cost, %s, item_id, user_id FROM IS601_S_Cart c WHERE c.user_id = %s""",
            order_id, current_user.get_id())
            if not result.status:
                flash("Error recording order history", "danger")
                has_error = True
                DB.getDB().rollback()
        # update stock based on cart data
        if not has_error:
            result = DB.update("""
            UPDATE IS601_S_Items 
                set stock = stock - (select IFNULL(quantity, 0) FROM IS601_S_Cart WHERE item_id = IS601_S_Items.id and user_id = %(uid)s) 
                WHERE id in (SELECT item_id from IS601_S_Cart where user_id = %(uid)s)
            """, {"uid":current_user.get_id()} )
            if not result.status:
                flash("Error updating stock", "danger")
                has_error = True
                DB.getDB().rollback()

        # apply purchase (specific to my project)
        if not has_error:
            # here I'm using a known item_id to update my player's stats
            attrs = [("life", -1), ("speed", -2), ("fire_rate", -3), ("damage", -4), ("radius", -5)]
            for attr, target_id in attrs:
                try:
                    query = f"""
                    INSERT INTO IS601_S_Attributes (name, value, user_id)
                    VALUES (%(attr)s,
                    (SELECT IFNULL(SUM(quantity), 0) FROM IS601_S_OrderItems WHERE item_id = %(target_id)s and user_id = %(uid)s)
                     , %(uid)s)
                    ON DUPLICATE KEY UPDATE 
                    value = (SELECT IFNULL(SUM(quantity), 0) FROM IS601_S_OrderItems WHERE item_id = %(target_id)s and user_id = %(uid)s)
                    """
                    print(f"{attr} query", query)
                    result = DB.insertOne(query,
                    {"uid": current_user.get_id(),
                    "attr": attr,
                    "target_id": int(target_id)})
                except Exception as e:
                    print(f"Error updating attribute {attr}", e)
        # empty the cart
        if not has_error:
            result = DB.delete("DELETE FROM IS601_S_Cart WHERE user_id = %s", current_user.get_id())
    
        if not has_error:
            details = f"Spent {total} on {quantity} upgrades" # TBD
            current_user.account.remove_points(-total, reason="purchase", details=details)
            DB.getDB().commit()
            flash("Purchase successful!", "success")
        else:
            return redirect(url_for("shop.cart"))
    except Exception as e:
        print("Transaction exception", e)
        flash("Something went wrong", "danger")
        traceback.print_exc()
    # TODO route to thank you / summary page
    # TODO add link from cart page to this route
    return render_template("order_summary.html", rows=cart, order=order)

@shop.route("/orders", methods=["GET"])
@login_required
def orders():
    rows = []
    try:
        result = DB.selectAll("""
        SELECT id, total_spent, number_of_items, created FROM IS601_S_Orders WHERE user_id = %s
        """, current_user.get_id())
        if result.status and result.rows:
            rows = result.rows
    except Exception as e:
        print("Error getting orders", e)
        flash("Error fetching orders", "danger")
    return render_template("orders.html", rows=rows)

@shop.route("/order", methods=["GET"])
@login_required
def order():
    rows = []
    total = 0
    id = request.args.get("id")
    if not id:
        flash("Invalid order", "danger")
        return redirect(url_for("shop.orders"))
    try:
        # locking query to order_id and user_id so the user can see only their orders
        result = DB.selectAll("""
        SELECT name, oi.cost, oi.quantity, (oi.cost*oi.quantity) as subtotal FROM IS601_S_OrderItems oi JOIN IS601_S_Items i on oi.item_id = i.id WHERE order_id = %s ANd user_id = %s
        """, id, current_user.get_id())
        if result.status and result.rows:
            rows = result.rows
            total = sum(int(row["subtotal"]) for row in rows)
    except Exception as e:
        print("Error getting order", e)
        flash("Error fetching order", "danger")
    return render_template("order.html", rows=rows, total=total)

@shop.route("/itemdetails", methods=["GET","POST"])
@login_required
def itemdetails():
    form = ItemForm()
    id = request.args.get("id", form.id.data or None)
    if id:
        try:
            result = DB.selectOne("SELECT id, name, description, category, stock, unit_price, visibility FROM IS601_S_Products WHERE id = %s", id)
            if result.status and result.row:
                    row = result.row
        except Exception as e:
            print("Error fetching item", e)
            flash("Item not found", "danger")
    return render_template("item_details.html", row = row)
@shop.route("/")
def index():
    return render_template("index.html")