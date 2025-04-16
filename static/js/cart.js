/**
 * tryontrend Shopping Cart JavaScript
 * 
 * This script handles the shopping cart functionality, including:
 * - Adding items to cart
 * - Removing items from cart
 * - Updating item quantities
 * - Calculating subtotal, shipping, tax, and total
 * - Storing cart data in localStorage
 */

// Main Cart class
class FashionCoreCart {
    constructor(options = {}) {
        // Default settings
        this.settings = {
            cartItemsContainerId: 'cartItemsContainer',
            cartItemsListId: 'cartItemsList',
            cartItemCountId: 'cartItemCount',
            emptyCartMessageId: 'emptyCartMessage',
            subtotalId: 'subtotal',
            shippingId: 'shipping',
            taxId: 'tax',
            totalId: 'total',
            headerCartCountId: 'cart-count',

            cartStorageKey: 'cartItems',
            taxRate: 0.18, // 18% GST
            freeShippingThreshold: 1000,
            shippingCost: 100,

            onCartUpdate: null
        };

        // Merge options with default settings
        Object.assign(this.settings, options);

        // Initialize elements
        this.elements = {};

        // Initialize the cart
        this.init();
    }

    /**
     * Initialize the cart
     */
    init() {
        // Get DOM elements
        this.getElements();

        // Load cart items from localStorage
        this.loadCartItems();

        // Setup product page add to cart buttons
        this.setupAddToCartButtons();
    }

    /**
     * Get DOM elements
     */
    getElements() {
        const s = this.settings;
        const e = this.elements;

        // Cart elements
        e.cartItemsContainer = document.getElementById(s.cartItemsContainerId);
        e.cartItemsList = document.getElementById(s.cartItemsListId);
        e.cartItemCount = document.getElementById(s.cartItemCountId);
        e.emptyCartMessage = document.getElementById(s.emptyCartMessageId);
        e.subtotal = document.getElementById(s.subtotalId);
        e.shipping = document.getElementById(s.shippingId);
        e.tax = document.getElementById(s.taxId);
        e.total = document.getElementById(s.totalId);
        e.headerCartCount = document.getElementById(s.headerCartCountId);
    }

    /**
     * Setup add to cart buttons
     */
    setupAddToCartButtons() {
        // Product detail page add to cart button
        const addToCartBtn = document.querySelector('.add-to-cart-btn');
        if (addToCartBtn) {
            addToCartBtn.addEventListener('click', () => {
                const productId = addToCartBtn.getAttribute('data-product-id');
                const productName = addToCartBtn.getAttribute('data-product-name');
                const productPrice = parseFloat(addToCartBtn.getAttribute('data-product-price'));
                const productImage = addToCartBtn.getAttribute('data-product-image');

                // Add item to cart
                this.addToCart({
                    id: productId,
                    name: productName,
                    price: productPrice,
                    image: productImage,
                    quantity: 1,
                    brand: addToCartBtn.getAttribute('data-product-brand') || ''
                });

                // Show notification
                alert(`${productName} added to cart!`);
            });
        }

        // Product listing page add to cart buttons
        const productListAddToCartBtns = document.querySelectorAll('.product-card .add-to-cart-btn');
        productListAddToCartBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();

                const productId = btn.getAttribute('data-product-id');
                const productName = btn.getAttribute('data-product-name');
                const productPrice = parseFloat(btn.getAttribute('data-product-price'));
                const productImage = btn.getAttribute('data-product-image');

                // Add item to cart
                this.addToCart({
                    id: productId,
                    name: productName,
                    price: productPrice,
                    image: productImage,
                    quantity: 1,
                    brand: btn.getAttribute('data-product-brand') || ''
                });

                // Show notification
                alert(`${productName} added to cart!`);
            });
        });
    }

    /**
     * Load cart items from localStorage
     */
    loadCartItems() {
        const cartItems = this.getCartItems();

        // Update cart count in header
        this.updateHeaderCartCount(cartItems);

        // If not on cart page, return
        if (!this.elements.cartItemsContainer) return;

        // Update cart count
        if (this.elements.cartItemCount) {
            this.elements.cartItemCount.textContent = `${cartItems.length} ${cartItems.length === 1 ? 'Item' : 'Items'}`;
        }

        // Show empty cart message if cart is empty
        if (cartItems.length === 0) {
            if (this.elements.emptyCartMessage) {
                this.elements.emptyCartMessage.style.display = 'flex';
            }
            if (this.elements.cartItemsList) {
                this.elements.cartItemsList.style.display = 'none';
            }
            this.updateOrderSummary(0);
            return;
        }

        // Hide empty cart message and show cart items
        if (this.elements.emptyCartMessage) {
            this.elements.emptyCartMessage.style.display = 'none';
        }
        if (this.elements.cartItemsList) {
            this.elements.cartItemsList.style.display = 'block';
        }

        // Calculate subtotal
        let subtotal = 0;

        // Clear existing cart items
        if (this.elements.cartItemsList) {
            this.elements.cartItemsList.innerHTML = '';

            // Add each cart item to the list
            cartItems.forEach((item, index) => {
                const itemSubtotal = item.price * item.quantity;
                subtotal += itemSubtotal;

                const cartItemElement = document.createElement('div');
                cartItemElement.className = 'cart-item';
                cartItemElement.innerHTML = `
                    <div class="item-image">
                        <img src="${item.image.startsWith('http') ? item.image : '/static/images/' + item.image}" alt="${item.name}">
                    </div>
                    <div class="item-details">
                        <h3 class="item-name">${item.name}</h3>
                        <p class="item-brand">${item.brand || 'Brand'}</p>
                        <p class="item-price">₹${item.price.toFixed(2)}</p>
                        <div class="item-actions">
                            <div class="quantity-control">
                                <button class="quantity-btn decrease-btn" data-index="${index}">-</button>
                                <input type="number" class="quantity-input" value="${item.quantity}" min="1" max="10" data-index="${index}">
                                <button class="quantity-btn increase-btn" data-index="${index}">+</button>
                            </div>
                            <button class="remove-btn" data-index="${index}">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                    <div class="total-price">₹${itemSubtotal.toFixed(2)}</div>
                `;

                this.elements.cartItemsList.appendChild(cartItemElement);
            });
        }

        // Update order summary
        this.updateOrderSummary(subtotal);

        // Add event listeners to quantity buttons and remove buttons
        this.setupCartEventListeners();
    }

    /**
     * Update order summary
     */
    updateOrderSummary(subtotal) {
        if (!this.elements.subtotal) return;

        // Calculate shipping (free for orders over threshold)
        const shipping = subtotal > this.settings.freeShippingThreshold ? 0 : this.settings.shippingCost;

        // Calculate tax
        const tax = subtotal * this.settings.taxRate;

        // Calculate total
        const total = subtotal + shipping + tax;

        // Update elements
        this.elements.subtotal.textContent = `₹${subtotal.toFixed(2)}`;
        this.elements.shipping.textContent = shipping === 0 ? 'Free' : `₹${shipping.toFixed(2)}`;
        this.elements.tax.textContent = `₹${tax.toFixed(2)}`;
        this.elements.total.textContent = `₹${total.toFixed(2)}`;
    }

    /**
     * Setup cart event listeners
     */
    setupCartEventListeners() {
        // Decrease quantity buttons
        document.querySelectorAll('.decrease-btn').forEach(button => {
            button.addEventListener('click', () => {
                const index = parseInt(button.getAttribute('data-index'));
                this.updateQuantity(index, -1);
            });
        });

        // Increase quantity buttons
        document.querySelectorAll('.increase-btn').forEach(button => {
            button.addEventListener('click', () => {
                const index = parseInt(button.getAttribute('data-index'));
                this.updateQuantity(index, 1);
            });
        });

        // Quantity inputs
        document.querySelectorAll('.quantity-input').forEach(input => {
            input.addEventListener('change', () => {
                const index = parseInt(input.getAttribute('data-index'));
                const newQuantity = parseInt(input.value);
                this.setQuantity(index, newQuantity);
            });
        });

        // Remove buttons
        document.querySelectorAll('.remove-btn').forEach(button => {
            button.addEventListener('click', () => {
                const index = parseInt(button.getAttribute('data-index'));
                this.removeItem(index);
            });
        });
    }

    /**
     * Get cart items from localStorage
     */
    getCartItems() {
        return JSON.parse(localStorage.getItem(this.settings.cartStorageKey)) || [];
    }

    /**
     * Save cart items to localStorage
     */
    saveCartItems(cartItems) {
        localStorage.setItem(this.settings.cartStorageKey, JSON.stringify(cartItems));

        // Update cart count in header
        this.updateHeaderCartCount(cartItems);

        // Call the onCartUpdate callback if provided
        if (this.settings.onCartUpdate) {
            this.settings.onCartUpdate(cartItems);
        }
    }

    /**
     * Update header cart count
     */
    updateHeaderCartCount(cartItems) {
        if (!this.elements.headerCartCount) return;

        const totalItems = cartItems.reduce((total, item) => total + item.quantity, 0);
        this.elements.headerCartCount.textContent = totalItems;
    }

    /**
     * Add item to cart
     */
    addToCart(item) {
        const cartItems = this.getCartItems();

        // Check if item already exists in cart
        const existingItemIndex = cartItems.findIndex(cartItem => cartItem.id === item.id);

        if (existingItemIndex > -1) {
            // Update quantity if item exists
            cartItems[existingItemIndex].quantity += item.quantity;
        } else {
            // Add new item if it doesn't exist
            cartItems.push(item);
        }

        // Save updated cart
        this.saveCartItems(cartItems);

        // Reload cart items if on cart page
        if (this.elements.cartItemsContainer) {
            this.loadCartItems();
        }
    }

    /**
     * Update quantity of an item
     */
    updateQuantity(index, change) {
        const cartItems = this.getCartItems();

        if (cartItems[index]) {
            const newQuantity = cartItems[index].quantity + change;

            if (newQuantity >= 1 && newQuantity <= 10) {
                cartItems[index].quantity = newQuantity;
                this.saveCartItems(cartItems);
                this.loadCartItems();
            }
        }
    }

    /**
     * Set quantity of an item
     */
    setQuantity(index, quantity) {
        const cartItems = this.getCartItems();

        if (cartItems[index] && quantity >= 1 && quantity <= 10) {
            cartItems[index].quantity = quantity;
            this.saveCartItems(cartItems);
            this.loadCartItems();
        }
    }

    /**
     * Remove an item from the cart
     */
    removeItem(index) {
        const cartItems = this.getCartItems();

        if (cartItems[index]) {
            cartItems.splice(index, 1);
            this.saveCartItems(cartItems);
            this.loadCartItems();
        }
    }

    /**
     * Clear the cart
     */
    clearCart() {
        this.saveCartItems([]);

        // Reload cart items if on cart page
        if (this.elements.cartItemsContainer) {
            this.loadCartItems();
        }
    }
}

// Export the FashionCoreCart class
if (typeof module !== 'undefined' && typeof module.exports !== 'undefined') {
    module.exports = FashionCoreCart;
} else {
    window.FashionCoreCart = FashionCoreCart;
}

// Initialize the cart when the DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    // Initialize the cart with default settings
    new FashionCoreCart();
});