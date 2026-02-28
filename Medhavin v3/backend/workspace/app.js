// Get cart list element
const cartList = document.getElementById("cart-list");

// Get order summary elements
const subtotalSpan = document.getElementById("subtotal");
const taxSpan = document.getElementById("tax");
const totalSpan = document.getElementById("total");

// Get checkout button element
const checkoutButton = document.getElementById("checkout-button");

// Initialize cart
let cart = JSON.parse(localStorage.getItem("cart")) || [];

// Render cart items function
function renderCartItems() {
    cartList.innerHTML = "";
    cart.forEach((item, index) => {
        const cartItem = document.createElement("li");
        cartItem.classList.add("cart-item");
        cartItem.innerHTML = `
            <h3>${item.name}</h3>
            <p>Price: $${item.price}</p>
            <p>Quantity: <span id="quantity-${index}">1</span></p>
            <button class="quantity-button" onclick="decreaseQuantity(${index})">-</button>
            <button class="quantity-button" onclick="increaseQuantity(${index})">+</button>
            <button class="remove-button" onclick="removeItem(${index})">Remove</button>
        `;
        cartList.appendChild(cartItem);
    });
    updateOrderSummary();
}

// Update order summary function
function updateOrderSummary() {
    const subtotal = cart.reduce((acc, item) => acc + item.price, 0);
    const tax = subtotal * 0.1;
    const total = subtotal + tax;
    subtotalSpan.textContent = subtotal.toFixed(2);
    taxSpan.textContent = tax.toFixed(2);
    totalSpan.textContent = total.toFixed(2);
}

// Decrease quantity function
function decreaseQuantity(index) {
    if (cart[index].quantity > 1) {
        cart[index].quantity--;
        renderCartItems();
    }
}

// Increase quantity function
function increaseQuantity(index) {
    cart[index].quantity++;
    renderCartItems();
}

// Remove item function
function removeItem(index) {
    cart.splice(index, 1);
    renderCartItems();
}

// Checkout function
function checkout() {
    // Implement checkout logic here
    alert("Checkout successful!");
}

// Add event listener to checkout button
checkoutButton.addEventListener("click", checkout);

// Initialize app
document.addEventListener("DOMContentLoaded", () => {
    renderCartItems();
});