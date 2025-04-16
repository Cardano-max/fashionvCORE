/**
 * tryontrend - Admin Dashboard JavaScript
 * Version: 1.0.0
 * Last updated: March 2025
 * 
 * This file handles all admin dashboard functionality including:
 * - Dashboard analytics and charts
 * - CRUD operations for products, orders, users
 * - Admin panel navigation and responsiveness
 * - Data tables with sorting and filtering
 * - Form validation
 */

// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function () {
    // Initialize the Admin Dashboard controller
    const AdminDashboard = {
        // DOM Elements
        elements: {
            // Core elements
            adminSidebar: document.querySelector('.admin-sidebar'),
            adminContent: document.querySelector('.admin-content'),
            adminNavLinks: document.querySelectorAll('.admin-nav-link'),

            // Charts
            salesChart: document.getElementById('salesChart'),
            statusChart: document.getElementById('statusChart'),

            // User management
            userTable: document.querySelector('.user-table'),
            addUserBtn: document.getElementById('addUserBtn'),
            userForm: document.getElementById('userForm'),
            userModal: document.getElementById('userModal'),
            modalClose: document.getElementById('modalClose'),
            saveUserBtn: document.getElementById('saveUserBtn'),
            cancelBtn: document.getElementById('cancelBtn'),
            deleteUserBtns: document.querySelectorAll('.delete-user-btn'),
            editUserBtns: document.querySelectorAll('.edit-user-btn'),
            addCreditsBtns: document.querySelectorAll('.add-credits-btn'),
            creditsUserId: document.getElementById('creditsUserId'),
            creditsAmount: document.getElementById('creditsAmount'),
            addCreditsBtn: document.getElementById('addCreditsBtn'),

            // Product management
            productTable: document.querySelector('.product-table'),
            addProductBtn: document.getElementById('addProductBtn'),
            productForm: document.getElementById('productForm'),
            productModal: document.getElementById('productModal'),
            saveProductBtn: document.getElementById('saveProductBtn'),
            editProductBtns: document.querySelectorAll('.edit-product-btn'),
            deleteProductBtns: document.querySelectorAll('.delete-product-btn'),

            // Order management
            orderTable: document.querySelector('.order-table'),
            viewOrderBtns: document.querySelectorAll('.view-order-btn'),
            cancelOrderBtns: document.querySelectorAll('.cancel-order-btn'),
            confirmCancelBtn: document.getElementById('confirmCancelBtn'),
            cancelOrderId: document.getElementById('cancelOrderId'),
            filterDropdowns: document.querySelectorAll('.filter-dropdown'),
            filterBtns: document.querySelectorAll('.filter-btn'),
            filterMenus: document.querySelectorAll('.filter-menu'),

            // Search functionality
            searchForms: document.querySelectorAll('.search-form'),
            searchInputs: document.querySelectorAll('.search-input')
        },

        // Application state
        state: {
            currentPage: window.location.pathname.split('/').pop(),
            charts: {},
            datatables: {},
            filters: {
                users: { role: 'all', status: 'all' },
                products: { category: 'all', sort: 'newest' },
                orders: { status: 'all', date: 'all' }
            }
        },

        // Initialize the controller
        init: function () {
            // Set current page in state
            this.setCurrentPage();

            // Initialize sidebar
            this.initSidebar();

            // Set up global event listeners
            this.bindGlobalEvents();

            // Initialize page-specific features
            this.initPageSpecificFeatures();

            // Initialize data tables if DataTables library is loaded
            this.initDataTables();
        },

        // Set current page based on URL
        setCurrentPage: function () {
            const path = window.location.pathname;
            if (path.includes('users')) {
                this.state.currentPage = 'users';
            } else if (path.includes('products')) {
                this.state.currentPage = 'products';
            } else if (path.includes('orders')) {
                this.state.currentPage = 'orders';
            } else {
                this.state.currentPage = 'dashboard'; // Default page
            }
        },

        // Initialize sidebar and navigation
        initSidebar: function () {
            const self = this;

            // Highlight current page in sidebar
            this.elements.adminNavLinks.forEach(link => {
                const href = link.getAttribute('href');
                if (href.includes(this.state.currentPage)) {
                    link.classList.add('active');
                } else {
                    link.classList.remove('active');
                }
            });

            // Add click event for mobile sidebar toggle
            const sidebarToggle = document.querySelector('.sidebar-toggle');
            if (sidebarToggle && this.elements.adminSidebar) {
                sidebarToggle.addEventListener('click', function () {
                    self.elements.adminSidebar.classList.toggle('active');
                    this.classList.toggle('active');
                });
            }

            // Add click event outside sidebar to close on mobile
            document.addEventListener('click', function (e) {
                if (self.elements.adminSidebar &&
                    self.elements.adminSidebar.classList.contains('active') &&
                    !self.elements.adminSidebar.contains(e.target) &&
                    !e.target.closest('.sidebar-toggle')) {
                    self.elements.adminSidebar.classList.remove('active');
                    if (sidebarToggle) {
                        sidebarToggle.classList.remove('active');
                    }
                }
            });
        },

        // Bind global events
        bindGlobalEvents: function () {
            const self = this;

            // Setup filter dropdowns
            if (this.elements.filterBtns) {
                this.elements.filterBtns.forEach((btn, index) => {
                    btn.addEventListener('click', function () {
                        // Toggle clicked menu
                        self.elements.filterMenus[index].classList.toggle('show');

                        // Close other menus
                        self.elements.filterMenus.forEach((menu, menuIndex) => {
                            if (menuIndex !== index) {
                                menu.classList.remove('show');
                            }
                        });
                    });
                });

                // Close filter menus when clicking outside
                document.addEventListener('click', function (e) {
                    if (!e.target.closest('.filter-dropdown')) {
                        self.elements.filterMenus.forEach(menu => {
                            menu.classList.remove('show');
                        });
                    }
                });
            }

            // Setup search functionality
            this.elements.searchForms.forEach(form => {
                form.addEventListener('submit', function (e) {
                    const input = this.querySelector('.search-input');
                    if (input && input.value.trim() === '') {
                        e.preventDefault();
                        self.showNotification('Please enter a search term', 'warning');
                    }
                });
            });

            // Close modals when clicking outside
            window.addEventListener('click', function (e) {
                const modals = document.querySelectorAll('.modal');
                modals.forEach(modal => {
                    if (e.target === modal) {
                        modal.classList.remove('show');
                    }
                });
            });

            // Set up export buttons
            document.querySelectorAll('.export-btn').forEach(btn => {
                btn.addEventListener('click', function () {
                    const type = this.getAttribute('data-export-type') || 'csv';
                    const table = this.getAttribute('data-table');

                    if (table) {
                        self.exportTable(table, type);
                    }
                });
            });
        },

        // Initialize page-specific features
        initPageSpecificFeatures: function () {
            switch (this.state.currentPage) {
                case 'dashboard':
                    this.initDashboard();
                    break;
                case 'users':
                    this.initUserManagement();
                    break;
                case 'products':
                    this.initProductManagement();
                    break;
                case 'orders':
                    this.initOrderManagement();
                    break;
            }
        },

        // Initialize dashboard 
        initDashboard: function () {
            // Initialize charts if Chart.js is loaded
            if (typeof Chart !== 'undefined') {
                this.initializeCharts();
            } else {
                console.warn('Chart.js is not loaded. Charts will not be displayed.');
            }

            // Setup real-time updates
            this.setupRealTimeUpdates();

            // Initialize recent activity list
            this.initRecentActivity();
        },

        // Initialize charts
        initializeCharts: function () {
            // Sales Chart
            if (this.elements.salesChart) {
                const salesCtx = this.elements.salesChart.getContext('2d');
                this.state.charts.sales = new Chart(salesCtx, {
                    type: 'line',
                    data: {
                        labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
                        datasets: [{
                            label: 'Sales (₹)',
                            data: [120000, 135000, 125000, 150000, 160000, 178000, 190000, 205000, 220000, 235000, 240000, 250000],
                            backgroundColor: 'rgba(67, 97, 238, 0.1)',
                            borderColor: 'rgba(67, 97, 238, 1)',
                            borderWidth: 2,
                            tension: 0.3,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    callback: function (value) {
                                        return '₹' + value / 1000 + 'K';
                                    }
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                display: false
                            },
                            tooltip: {
                                callbacks: {
                                    label: function (context) {
                                        return '₹' + context.raw.toLocaleString();
                                    }
                                }
                            }
                        },
                        animations: {
                            tension: {
                                duration: 1000,
                                easing: 'linear',
                                from: 0.8,
                                to: 0.3,
                                loop: false
                            }
                        }
                    }
                });
            }

            // Order Status Chart
            if (this.elements.statusChart) {
                const statusCtx = this.elements.statusChart.getContext('2d');
                this.state.charts.status = new Chart(statusCtx, {
                    type: 'doughnut',
                    data: {
                        labels: ['Completed', 'Processing', 'Pending', 'Cancelled'],
                        datasets: [{
                            data: [65, 20, 10, 5],
                            backgroundColor: [
                                'rgba(16, 185, 129, 0.8)',
                                'rgba(67, 97, 238, 0.8)',
                                'rgba(245, 158, 11, 0.8)',
                                'rgba(239, 68, 68, 0.8)'
                            ],
                            borderColor: [
                                'rgba(16, 185, 129, 1)',
                                'rgba(67, 97, 238, 1)',
                                'rgba(245, 158, 11, 1)',
                                'rgba(239, 68, 68, 1)'
                            ],
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'bottom'
                            },
                            tooltip: {
                                callbacks: {
                                    label: function (context) {
                                        return context.label + ': ' + context.raw + '%';
                                    }
                                }
                            }
                        },
                        animation: {
                            animateRotate: true,
                            animateScale: true
                        }
                    }
                });
            }
        },

        // Setup real-time updates simulation
        setupRealTimeUpdates: function () {
            // In a real application, this would use WebSockets or Server-Sent Events
            // For demo purposes, we're using a timer to simulate real-time updates
            const self = this;

            // Update dashboard stats every 30 seconds
            setInterval(() => {
                // Update sales chart with random data
                if (self.state.charts.sales) {
                    // Get current data
                    const data = self.state.charts.sales.data.datasets[0].data;

                    // Update with slight random variations
                    const newData = data.map(value => {
                        const change = Math.random() * 10000 - 5000; // Random change between -5000 and +5000
                        return Math.max(100000, value + change); // Ensure value doesn't go below 100k
                    });

                    // Update chart
                    self.state.charts.sales.data.datasets[0].data = newData;
                    self.state.charts.sales.update();
                }

                // Update stat cards with slight variations
                document.querySelectorAll('.stat-value').forEach(stat => {
                    const currentValue = parseInt(stat.textContent.replace(/[^0-9]/g, ''));
                    if (!isNaN(currentValue)) {
                        // Add a small random variation
                        const variation = Math.floor(Math.random() * 5) - 2; // Random value between -2 and +2
                        stat.textContent = stat.textContent.replace(
                            currentValue.toString(),
                            (currentValue + variation).toString()
                        );
                    }
                });
            }, 30000);
        },

        // Initialize recent activity
        initRecentActivity: function () {
            // This would fetch real activity data in a production environment
            // For demo, we'll just add animation to existing items
            const activityItems = document.querySelectorAll('.activity-item');

            activityItems.forEach((item, index) => {
                // Add staggered animations
                setTimeout(() => {
                    item.classList.add('animate-fade-in');
                }, index * 100);
            });
        },

        // Initialize user management
        initUserManagement: function () {
            const self = this;

            // Add user button
            if (this.elements.addUserBtn && this.elements.userModal) {
                this.elements.addUserBtn.addEventListener('click', function () {
                    document.getElementById('modalTitle').textContent = 'Add User';
                    self.elements.userForm.reset();
                    self.elements.userForm.elements.id.value = '';
                    self.elements.userForm.elements.credits.value = '3';
                    self.elements.userForm.elements.is_active.checked = true;
                    self.elements.userModal.classList.add('show');
                });
            }

            // Edit user buttons
            if (this.elements.editUserBtns) {
                this.elements.editUserBtns.forEach(btn => {
                    btn.addEventListener('click', function () {
                        const userId = this.getAttribute('data-id');
                        document.getElementById('modalTitle').textContent = 'Edit User';

                        // In a real app, you would fetch user data from server
                        // This is just a simplified example using data attributes
                        const userRow = btn.closest('tr');
                        const username = userRow.querySelector('.user-name').textContent;
                        const email = userRow.querySelector('.user-email').textContent;
                        const isAdmin = userRow.querySelector('.user-role').textContent.trim() === 'Admin';
                        const credits = userRow.querySelector('.credits-badge').textContent;

                        // Set form values
                        self.elements.userForm.elements.id.value = userId;
                        self.elements.userForm.elements.username.value = username;
                        self.elements.userForm.elements.email.value = email;
                        self.elements.userForm.elements.password.value = '';
                        self.elements.userForm.elements.credits.value = credits;
                        self.elements.userForm.elements.is_admin.checked = isAdmin;
                        self.elements.userForm.elements.is_active.checked = true;

                        self.elements.userModal.classList.add('show');
                    });
                });
            }

            // Add credits buttons
            if (this.elements.addCreditsBtns) {
                this.elements.addCreditsBtns.forEach(btn => {
                    btn.addEventListener('click', function () {
                        const userId = this.getAttribute('data-id');
                        self.elements.creditsUserId.value = userId;
                        document.getElementById('creditsModal').classList.add('show');
                    });
                });
            }

            // Add credits submit
            if (this.elements.addCreditsBtn) {
                this.elements.addCreditsBtn.addEventListener('click', function () {
                    const userId = self.elements.creditsUserId.value;
                    const creditsAmount = self.elements.creditsAmount.value;

                    // In a real app, you would send this to the server
                    // For demo, we'll just show a notification
                    self.showNotification(`Added ${creditsAmount} credits to user ID ${userId}`, 'success');
                    document.getElementById('creditsModal').classList.remove('show');

                    // Update UI
                    const userRow = document.querySelector(`tr[data-user-id="${userId}"]`);
                    if (userRow) {
                        const creditsDisplay = userRow.querySelector('.credits-badge');
                        if (creditsDisplay) {
                            const currentCredits = parseInt(creditsDisplay.textContent);
                            const newCredits = currentCredits + parseInt(creditsAmount);
                            creditsDisplay.textContent = newCredits;

                            // Add animation
                            creditsDisplay.classList.add('animate-pulse');
                            setTimeout(() => {
                                creditsDisplay.classList.remove('animate-pulse');
                            }, 1000);
                        }
                    }
                });
            }

            // Delete user buttons
            if (this.elements.deleteUserBtns) {
                this.elements.deleteUserBtns.forEach(btn => {
                    btn.addEventListener('click', function () {
                        const userId = this.getAttribute('data-id');
                        document.getElementById('deleteUserId').value = userId;
                        document.getElementById('deleteModal').classList.add('show');
                    });
                });
            }

            // Confirm delete user
            const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
            if (confirmDeleteBtn) {
                confirmDeleteBtn.addEventListener('click', function () {
                    const userId = document.getElementById('deleteUserId').value;

                    // In a real app, you would send delete request to server
                    // For demo, we'll just remove the row and show a notification
                    const userRow = document.querySelector(`tr[data-user-id="${userId}"]`);
                    if (userRow) {
                        // Add fade out animation
                        userRow.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                        userRow.style.opacity = '0';
                        userRow.style.transform = 'translateX(20px)';

                        // Remove row after animation
                        setTimeout(() => {
                            userRow.remove();
                        }, 500);
                    }

                    self.showNotification(`User ID ${userId} deleted successfully!`, 'success');
                    document.getElementById('deleteModal').classList.remove('show');
                });
            }

            // Save user button
            if (this.elements.saveUserBtn) {
                this.elements.saveUserBtn.addEventListener('click', function () {
                    // Validate form
                    if (!self.validateForm(self.elements.userForm)) {
                        return;
                    }

                    // Get form data
                    const formData = new FormData(self.elements.userForm);
                    const userData = Object.fromEntries(formData.entries());

                    // In a real app, you would send this to the server
                    // For demo, we'll just show a notification
                    self.showNotification('User saved successfully!', 'success');
                    self.elements.userModal.classList.remove('show');

                    // Clear form
                    self.elements.userForm.reset();
                });
            }

            // Modal close buttons
            document.querySelectorAll('.modal-close, #cancelBtn, #cancelCreditsBtn, #cancelDeleteBtn').forEach(btn => {
                btn.addEventListener('click', function () {
                    const modal = this.closest('.modal');
                    if (modal) {
                        modal.classList.remove('show');
                    }
                });
            });
        },

        // Initialize product management
        initProductManagement: function () {
            const self = this;

            // Add product button
            if (this.elements.addProductBtn && this.elements.productModal) {
                this.elements.addProductBtn.addEventListener('click', function () {
                    document.getElementById('modalTitle').textContent = 'Add Product';
                    self.elements.productForm.reset();
                    self.elements.productForm.elements.id.value = '';
                    self.elements.productModal.classList.add('show');
                });
            }

            // Edit product buttons
            if (this.elements.editProductBtns) {
                this.elements.editProductBtns.forEach(btn => {
                    btn.addEventListener('click', function () {
                        const productId = this.getAttribute('data-id');
                        document.getElementById('modalTitle').textContent = 'Edit Product';

                        // In a real app, you would fetch product data from server
                        // This is just a simplified example
                        const productRow = btn.closest('tr');
                        const name = productRow.cells[2].textContent;
                        const category = productRow.cells[3].textContent;
                        const brand = productRow.cells[4].textContent;
                        const price = productRow.cells[5].textContent.replace('₹', '');
                        const stock = productRow.cells[6].textContent;

                        // Set form values
                        self.elements.productForm.elements.id.value = productId;
                        self.elements.productForm.elements.name.value = name;
                        self.elements.productForm.elements.category.value = category;
                        self.elements.productForm.elements.brand.value = brand;
                        self.elements.productForm.elements.price.value = price;
                        self.elements.productForm.elements.stock.value = stock;

                        self.elements.productModal.classList.add('show');
                    });
                });
            }

            // Delete product buttons
            if (this.elements.deleteProductBtns) {
                this.elements.deleteProductBtns.forEach(btn => {
                    btn.addEventListener('click', function () {
                        const productId = this.getAttribute('data-id');
                        document.getElementById('deleteProductId').value = productId;
                        document.getElementById('deleteModal').classList.add('show');
                    });
                });
            }

            // Confirm delete product
            const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
            if (confirmDeleteBtn) {
                confirmDeleteBtn.addEventListener('click', function () {
                    const productId = document.getElementById('deleteProductId').value;

                    // In a real app, you would send delete request to server
                    // For demo, we'll just remove the row and show a notification
                    const productRow = document.querySelector(`tr[data-product-id="${productId}"]`);
                    if (productRow) {
                        // Add fade out animation
                        productRow.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                        productRow.style.opacity = '0';
                        productRow.style.transform = 'translateX(20px)';

                        // Remove row after animation
                        setTimeout(() => {
                            productRow.remove();
                        }, 500);
                    }

                    self.showNotification(`Product ID ${productId} deleted successfully!`, 'success');
                    document.getElementById('deleteModal').classList.remove('show');
                });
            }

            // Save product button
            if (this.elements.saveProductBtn) {
                this.elements.saveProductBtn.addEventListener('click', function () {
                    // Validate form
                    if (!self.validateForm(self.elements.productForm)) {
                        return;
                    }

                    // Get form data
                    const formData = new FormData(self.elements.productForm);
                    const productData = Object.fromEntries(formData.entries());

                    // In a real app, you would send this to the server
                    // For demo, we'll just show a notification
                    self.showNotification('Product saved successfully!', 'success');
                    self.elements.productModal.classList.remove('show');

                    // If this is an edit, update the table row
                    if (productData.id) {
                        const productRow = document.querySelector(`tr[data-product-id="${productData.id}"]`);
                        if (productRow) {
                            // Update row cells
                            productRow.cells[2].textContent = productData.name;
                            productRow.cells[3].textContent = productData.category;
                            productRow.cells[4].textContent = productData.brand;
                            productRow.cells[5].textContent = `₹${parseFloat(productData.price).toFixed(2)}`;
                            productRow.cells[6].textContent = productData.stock;

                            // Add animation
                            productRow.classList.add('highlight-row');
                            setTimeout(() => {
                                productRow.classList.remove('highlight-row');
                            }, 2000);
                        }
                    }

                    // Clear form
                    self.elements.productForm.reset();
                });
            }

            // File input preview (for product image)
            const productImage = document.getElementById('productImage');
            const imagePreview = document.getElementById('imagePreview');

            if (productImage && imagePreview) {
                productImage.addEventListener('change', function () {
                    if (this.files && this.files[0]) {
                        const reader = new FileReader();

                        reader.onload = function (e) {
                            imagePreview.innerHTML = `<img src="${e.target.result}" alt="Preview">`;
                            imagePreview.style.display = 'block';
                        };

                        reader.readAsDataURL(this.files[0]);
                    }
                });
            }
        },

        // Initialize order management
        initOrderManagement: function () {
            const self = this;

            // View order buttons
            if (this.elements.viewOrderBtns) {
                this.elements.viewOrderBtns.forEach(btn => {
                    btn.addEventListener('click', function () {
                        const orderId = this.getAttribute('data-id');

                        // In a real app, you would fetch order details from the server
                        // For demo, we'll just show the modal with some sample data
                        const orderModal = document.getElementById('orderModal');
                        orderModal.querySelector('.modal-title').textContent = `Order #${orderId}`;
                        orderModal.classList.add('show');
                    });
                });
            }

            // Cancel order buttons
            if (this.elements.cancelOrderBtns) {
                this.elements.cancelOrderBtns.forEach(btn => {
                    btn.addEventListener('click', function () {
                        const orderId = this.getAttribute('data-id');
                        self.elements.cancelOrderId.value = orderId;
                        document.getElementById('cancelModal').classList.add('show');
                    });
                });
            }

            // Confirm cancel order
            if (this.elements.confirmCancelBtn) {
                this.elements.confirmCancelBtn.addEventListener('click', function () {
                    const orderId = self.elements.cancelOrderId.value;

                    // In a real app, you would send cancel request to server
                    // For demo, we'll just update the status and show a notification
                    const orderRow = document.querySelector(`tr[data-order-id="${orderId}"]`);
                    if (orderRow) {
                        const statusCell = orderRow.querySelector('.order-status');
                        if (statusCell) {
                            // Update status
                            statusCell.className = 'order-status status-cancelled';
                            statusCell.textContent = 'Cancelled';

                            // Add animation
                            statusCell.classList.add('animate-pulse');
                            setTimeout(() => {
                                statusCell.classList.remove('animate-pulse');
                            }, 1000);
                        }
                    }

                    self.showNotification(`Order ID ${orderId} cancelled successfully!`, 'success');
                    document.getElementById('cancelModal').classList.remove('show');
                });
            }

            // Status filter
            document.querySelectorAll('input[name="status"]').forEach(input => {
                input.addEventListener('change', function () {
                    self.filterOrders('status', this.value);
                });
            });

            // Date filter
            document.querySelectorAll('input[name="date"]').forEach(input => {
                input.addEventListener('change', function () {
                    self.filterOrders('date', this.value);
                });
            });
        },

        // Filter orders
        filterOrders: function (filterType, value) {
            // Update filter state
            this.state.filters.orders[filterType] = value;

            // Get all order rows
            const orderRows = document.querySelectorAll('.order-table tbody tr');
            if (!orderRows.length) return;

            // Apply filters
            orderRows.forEach(row => {
                let showRow = true;

                // Filter by status
                if (this.state.filters.orders.status !== 'all') {
                    const statusElement = row.querySelector('.order-status');
                    if (statusElement) {
                        const statusClass = `status-${this.state.filters.orders.status}`;
                        if (!statusElement.classList.contains(statusClass)) {
                            showRow = false;
                        }
                    }
                }

                // Filter by date
                if (showRow && this.state.filters.orders.date !== 'all') {
                    const dateCell = row.cells[2].textContent;
                    const orderDate = new Date(dateCell);
                    const now = new Date();

                    switch (this.state.filters.orders.date) {
                        case 'today':
                            // Check if same day
                            if (orderDate.toDateString() !== now.toDateString()) {
                                showRow = false;
                            }
                            break;
                        case 'week':
                            // Check if within last 7 days
                            const weekAgo = new Date();
                            weekAgo.setDate(now.getDate() - 7);
                            if (orderDate < weekAgo) {
                                showRow = false;
                            }
                            break;
                        case 'month':
                            // Check if within last 30 days
                            const monthAgo = new Date();
                            monthAgo.setDate(now.getDate() - 30);
                            if (orderDate < monthAgo) {
                                showRow = false;
                            }
                            break;
                    }
                }

                // Show or hide row
                if (showRow) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        },

        // Initialize DataTables
        initDataTables: function () {
            // Check if DataTables is loaded
            if (typeof $.fn.DataTable !== 'undefined') {
                // Initialize user table
                if (this.elements.userTable) {
                    this.state.datatables.users = $(this.elements.userTable).DataTable({
                        responsive: true,
                        language: {
                            search: "_INPUT_",
                            searchPlaceholder: "Search users...",
                            lengthMenu: "Show _MENU_ users per page",
                            info: "Showing _START_ to _END_ of _TOTAL_ users"
                        },
                        dom: '<"top"lf>rt<"bottom"ip>',
                        lengthMenu: [10, 25, 50, 100],
                        pageLength: 10,
                        order: [[4, 'desc']] // Sort by joined date by default
                    });
                }

                // Initialize product table
                if (this.elements.productTable) {
                    this.state.datatables.products = $(this.elements.productTable).DataTable({
                        responsive: true,
                        language: {
                            search: "_INPUT_",
                            searchPlaceholder: "Search products...",
                            lengthMenu: "Show _MENU_ products per page",
                            info: "Showing _START_ to _END_ of _TOTAL_ products"
                        },
                        dom: '<"top"lf>rt<"bottom"ip>',
                        lengthMenu: [10, 25, 50, 100],
                        pageLength: 10,
                        order: [[0, 'desc']] // Sort by ID by default
                    });
                }

                // Initialize order table
                if (this.elements.orderTable) {
                    this.state.datatables.orders = $(this.elements.orderTable).DataTable({
                        responsive: true,
                        language: {
                            search: "_INPUT_",
                            searchPlaceholder: "Search orders...",
                            lengthMenu: "Show _MENU_ orders per page",
                            info: "Showing _START_ to _END_ of _TOTAL_ orders"
                        },
                        dom: '<"top"lf>rt<"bottom"ip>',
                        lengthMenu: [10, 25, 50, 100],
                        pageLength: 10,
                        order: [[2, 'desc']] // Sort by date by default
                    });
                }
            }
        },

        // Validate form
        validateForm: function (form) {
            let isValid = true;
            const requiredFields = form.querySelectorAll('[required]');

            // Reset previous validation
            form.querySelectorAll('.is-invalid').forEach(field => {
                field.classList.remove('is-invalid');
            });

            form.querySelectorAll('.invalid-feedback').forEach(feedback => {
                feedback.remove();
            });

            // Check required fields
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    isValid = false;
                    field.classList.add('is-invalid');

                    // Add error message
                    const feedback = document.createElement('div');
                    feedback.className = 'invalid-feedback';
                    feedback.textContent = 'This field is required';
                    field.parentNode.appendChild(feedback);
                }
            });

            // Check email format
            const emailField = form.querySelector('input[type="email"]');
            if (emailField && emailField.value.trim()) {
                const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                if (!emailRegex.test(emailField.value.trim())) {
                    isValid = false;
                    emailField.classList.add('is-invalid');

                    // Add error message
                    const feedback = document.createElement('div');
                    feedback.className = 'invalid-feedback';
                    feedback.textContent = 'Please enter a valid email address';
                    emailField.parentNode.appendChild(feedback);
                }
            }

            // Check numeric fields
            form.querySelectorAll('input[type="number"]').forEach(field => {
                if (field.value.trim() && isNaN(parseFloat(field.value))) {
                    isValid = false;
                    field.classList.add('is-invalid');

                    // Add error message
                    const feedback = document.createElement('div');
                    feedback.className = 'invalid-feedback';
                    feedback.textContent = 'Please enter a valid number';
                    field.parentNode.appendChild(feedback);
                }
            });

            return isValid;
        },

        // Export table data
        exportTable: function (tableId, type = 'csv') {
            const table = document.getElementById(tableId);
            if (!table) return;

            // Get table headers
            const headers = [];
            table.querySelectorAll('thead th').forEach(th => {
                headers.push(th.textContent.trim());
            });

            // Get table data
            const rows = [];
            table.querySelectorAll('tbody tr').forEach(tr => {
                const row = [];
                tr.querySelectorAll('td').forEach(td => {
                    // Get text content, removing any extra spaces
                    let text = td.textContent.trim().replace(/\s+/g, ' ');

                    // Skip action buttons
                    if (!td.querySelector('button')) {
                        row.push(text);
                    }
                });

                if (row.length > 0) {
                    rows.push(row);
                }
            });

            // Create CSV content
            let content = '';

            if (type === 'csv') {
                // Add headers
                content += headers.join(',') + '\n';

                // Add rows
                rows.forEach(row => {
                    content += row.map(cell => {
                        // Escape commas and quotes
                        if (cell.includes(',') || cell.includes('"')) {
                            return `"${cell.replace(/"/g, '""')}"`;
                        }
                        return cell;
                    }).join(',') + '\n';
                });

                // Download file
                this.downloadFile(content, `${tableId}-export.csv`, 'text/csv');
            } else if (type === 'json') {
                // Create JSON structure
                const jsonData = rows.map(row => {
                    const obj = {};
                    headers.forEach((header, index) => {
                        if (index < row.length) {
                            obj[header] = row[index];
                        }
                    });
                    return obj;
                });

                // Download file
                this.downloadFile(
                    JSON.stringify(jsonData, null, 2),
                    `${tableId}-export.json`,
                    'application/json'
                );
            }
        },

        // Download file
        downloadFile: function (content, fileName, mimeType) {
            const blob = new Blob([content], { type: mimeType });
            const url = URL.createObjectURL(blob);

            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            a.style.display = 'none';

            document.body.appendChild(a);
            a.click();

            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 100);
        },

        // Show notification
        showNotification: function (message, type = 'info') {
            // Check if notification container exists, create if not
            let notificationContainer = document.querySelector('.notification-container');
            if (!notificationContainer) {
                notificationContainer = document.createElement('div');
                notificationContainer.className = 'notification-container';
                document.body.appendChild(notificationContainer);
            }

            // Create notification element
            const notification = document.createElement('div');
            notification.className = `notification notification-${type}`;

            // Set icon based on type
            let icon = 'info-circle';
            if (type === 'success') icon = 'check-circle';
            if (type === 'error') icon = 'times-circle';
            if (type === 'warning') icon = 'exclamation-triangle';

            // Create notification content
            notification.innerHTML = `
                <div class="notification-icon"><i class="fas fa-${icon}"></i></div>
                <div class="notification-content">
                    <div class="notification-message">${message}</div>
                </div>
                <button class="notification-close">&times;</button>
                <div class="notification-progress"></div>
            `;

            // Add notification to container
            notificationContainer.appendChild(notification);

            // Add animation class after a small delay (for transition to work)
            setTimeout(() => {
                notification.classList.add('show');
            }, 10);

            // Add close event to notification
            const closeBtn = notification.querySelector('.notification-close');
            closeBtn.addEventListener('click', () => {
                notification.classList.remove('show');
                setTimeout(() => {
                    notification.remove();
                }, 300);
            });

            // Auto-remove notification after 5 seconds
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.classList.remove('show');
                    setTimeout(() => {
                        notification.remove();
                    }, 300);
                }
            }, 5000);
        }
    };

    // Initialize the Admin Dashboard
    AdminDashboard.init();
});