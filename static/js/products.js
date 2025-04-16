/**
 * tryontrend - Products Page JavaScript
 * Version: 1.0.0
 * Last updated: March 2025
 * 
 * This file handles all product-related functionality including:
 * - Product filtering and searching
 * - Category navigation
 * - Product card interactions
 * - Quick view functionality
 * - Add to cart integration
 * - Product image gallery
 * - Wishlist functionality
 */

// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function () {
    // Initialize the Products controller
    const ProductsController = {
        // DOM Elements
        elements: {
            productsGrid: document.querySelector('.products-grid'),
            searchInput: document.querySelector('.search-input'),
            searchForm: document.querySelector('.search-form'),
            categoryTags: document.querySelectorAll('.category-tag'),
            filterDropdowns: document.querySelectorAll('.filter-dropdown'),
            filterBtns: document.querySelectorAll('.filter-btn'),
            filterMenus: document.querySelectorAll('.filter-menu'),
            addToCartBtns: document.querySelectorAll('.add-to-cart-btn'),
            productCards: document.querySelectorAll('.product-card'),
            quickViewBtns: document.querySelectorAll('.quick-view-btn'),
            sortOptions: document.querySelectorAll('input[name="sort"]'),
            priceRangeMin: document.querySelector('#price-min'),
            priceRangeMax: document.querySelector('#price-max'),
            // Product detail page elements
            productMainImage: document.querySelector('.product-main-image img'),
            productThumbnails: document.querySelectorAll('.product-thumbnail'),
            quantityInput: document.querySelector('.quantity-input'),
            quantityIncBtn: document.querySelector('.quantity-inc'),
            quantityDecBtn: document.querySelector('.quantity-dec'),
            wishlistBtn: document.querySelector('.wishlist-btn'),
            shareBtn: document.querySelector('.share-btn'),
            colorOptions: document.querySelectorAll('.color-option'),
            sizeOptions: document.querySelectorAll('.size-option'),
        },

        // Application state
        state: {
            currentCategory: null,
            searchQuery: '',
            sortBy: 'newest', // Default sort option
            filters: {
                priceRange: { min: 0, max: 100000 },
                colors: [],
                sizes: [],
                inStock: true
            },
            quickViewProduct: null,
            selectedColor: null,
            selectedSize: null,
            wishlist: JSON.parse(localStorage.getItem('wishlist')) || [],
            recentlyViewed: JSON.parse(localStorage.getItem('recentlyViewed')) || [],
            quantity: 1
        },

        // Initialize the controller
        init: function () {
            this.bindEvents();
            this.initializeFilters();
            this.handleUrlParams();
            this.initProductDetailPage();
            this.initAnimations();

            // Initialize LazyLoad for images (if library is included)
            if (typeof LazyLoad !== 'undefined') {
                new LazyLoad({
                    elements_selector: ".lazy",
                    threshold: 300,
                    callback_loaded: (el) => {
                        // Add fade-in animation when image loads
                        el.classList.add('fade-in');
                    }
                });
            }
        },

        // Bind all event listeners
        bindEvents: function () {
            const self = this;
            const els = this.elements;

            // Search form submission
            if (els.searchForm) {
                els.searchForm.addEventListener('submit', function (e) {
                    if (els.searchInput.value.trim() === '') {
                        e.preventDefault(); // Prevent empty search submission
                        self.showToast('Please enter a search term', 'warning');
                    }
                });
            }

            // Search input live filtering (if on products page with JS filtering)
            if (els.searchInput && els.productsGrid && document.body.classList.contains('js-filter-enabled')) {
                els.searchInput.addEventListener('input', self.debounce(function () {
                    self.state.searchQuery = els.searchInput.value.trim().toLowerCase();
                    self.filterProducts();
                }, 300));
            }

            // Category tags
            if (els.categoryTags) {
                els.categoryTags.forEach(tag => {
                    tag.addEventListener('click', function (e) {
                        if (document.body.classList.contains('js-filter-enabled')) {
                            e.preventDefault();

                            // Remove active class from all tags
                            els.categoryTags.forEach(t => t.classList.remove('active'));

                            // Add active class to clicked tag
                            this.classList.add('active');

                            // Update current category
                            self.state.currentCategory = this.getAttribute('data-category') || null;

                            // Filter products
                            self.filterProducts();

                            // Update URL without page refresh
                            const url = new URL(window.location);
                            if (self.state.currentCategory) {
                                url.searchParams.set('category', self.state.currentCategory);
                            } else {
                                url.searchParams.delete('category');
                            }
                            window.history.pushState({}, '', url);
                        }
                    });
                });
            }

            // Filter dropdowns
            if (els.filterBtns) {
                els.filterBtns.forEach((btn, index) => {
                    btn.addEventListener('click', function () {
                        // Toggle clicked menu
                        els.filterMenus[index].classList.toggle('show');

                        // Close other menus
                        els.filterMenus.forEach((menu, menuIndex) => {
                            if (menuIndex !== index) {
                                menu.classList.remove('show');
                            }
                        });
                    });
                });

                // Close filter menus when clicking outside
                document.addEventListener('click', function (e) {
                    if (!e.target.closest('.filter-dropdown')) {
                        els.filterMenus.forEach(menu => {
                            menu.classList.remove('show');
                        });
                    }
                });
            }

            // Sort options
            if (els.sortOptions) {
                els.sortOptions.forEach(option => {
                    option.addEventListener('change', function () {
                        if (this.checked) {
                            self.state.sortBy = this.value;
                            self.sortProducts();
                        }
                    });
                });
            }

            // Price range inputs
            if (els.priceRangeMin && els.priceRangeMax) {
                els.priceRangeMin.addEventListener('change', function () {
                    self.state.filters.priceRange.min = parseInt(this.value) || 0;
                    self.filterProducts();
                });

                els.priceRangeMax.addEventListener('change', function () {
                    self.state.filters.priceRange.max = parseInt(this.value) || 100000;
                    self.filterProducts();
                });
            }

            // Add to cart buttons
            if (els.addToCartBtns) {
                els.addToCartBtns.forEach(btn => {
                    btn.addEventListener('click', function (e) {
                        e.preventDefault();

                        const productId = this.getAttribute('data-product-id');
                        const productName = this.getAttribute('data-product-name');
                        const productPrice = parseFloat(this.getAttribute('data-product-price'));
                        const productImage = this.getAttribute('data-product-image');
                        const productBrand = this.getAttribute('data-product-brand') || '';

                        // Add animation to the button
                        this.classList.add('animate-pulse');

                        // Get the product card for animation
                        const productCard = this.closest('.product-card');

                        // If the cart JavaScript is available, use it
                        if (typeof FashionCoreCart !== 'undefined') {
                            const cart = new FashionCoreCart();
                            cart.addToCart({
                                id: productId,
                                name: productName,
                                price: productPrice,
                                image: productImage,
                                brand: productBrand,
                                quantity: self.state.quantity || 1
                            });
                        } else {
                            // Fallback to basic localStorage implementation
                            self.addToCart({
                                id: productId,
                                name: productName,
                                price: productPrice,
                                image: productImage,
                                brand: productBrand,
                                quantity: self.state.quantity || 1
                            });
                        }

                        // Animate product card (if available)
                        if (productCard) {
                            productCard.classList.add('animate-added-to-cart');
                            setTimeout(() => {
                                productCard.classList.remove('animate-added-to-cart');
                            }, 700);
                        }

                        // Reset button animation after a delay
                        setTimeout(() => {
                            this.classList.remove('animate-pulse');
                        }, 700);

                        // Show success message
                        self.showToast(`${productName} added to cart!`, 'success');
                    });
                });
            }

            // Quick view buttons
            if (els.quickViewBtns) {
                els.quickViewBtns.forEach(btn => {
                    btn.addEventListener('click', function (e) {
                        e.preventDefault();

                        const productId = this.getAttribute('data-product-id');
                        self.openQuickView(productId);
                    });
                });
            }

            // Product cards hover effects and animations
            if (els.productCards) {
                els.productCards.forEach(card => {
                    // Add hover class on mouseenter
                    card.addEventListener('mouseenter', function () {
                        this.classList.add('hover');
                    });

                    // Remove hover class on mouseleave
                    card.addEventListener('mouseleave', function () {
                        this.classList.remove('hover');
                    });

                    // Add click event for cards that link to product detail
                    const productLink = card.querySelector('.product-link');
                    if (productLink) {
                        card.addEventListener('click', function (e) {
                            // Only navigate if the click wasn't on a button or another interactive element
                            if (!e.target.closest('button') && !e.target.closest('a:not(.product-link)')) {
                                window.location.href = productLink.getAttribute('href');
                            }
                        });
                    }
                });
            }
        },

        // Initialize product detail page specific elements
        initProductDetailPage: function () {
            const self = this;
            const els = this.elements;

            // Product thumbnails gallery
            if (els.productThumbnails && els.productMainImage) {
                els.productThumbnails.forEach(thumb => {
                    thumb.addEventListener('click', function () {
                        // Remove active class from all thumbnails
                        els.productThumbnails.forEach(t => t.classList.remove('active'));

                        // Add active class to clicked thumbnail
                        this.classList.add('active');

                        // Update main image
                        const imgSrc = this.querySelector('img').getAttribute('src');

                        // Fade out main image
                        els.productMainImage.style.opacity = '0';

                        // After fade out, update src and fade in
                        setTimeout(() => {
                            els.productMainImage.setAttribute('src', imgSrc);
                            els.productMainImage.style.opacity = '1';
                        }, 300);
                    });
                });
            }

            // Quantity controls
            if (els.quantityInput) {
                els.quantityInput.addEventListener('change', function () {
                    let value = parseInt(this.value);

                    // Ensure quantity is at least 1
                    if (isNaN(value) || value < 1) {
                        value = 1;
                        this.value = 1;
                    }

                    // Ensure quantity is not more than max (if set)
                    const max = parseInt(this.getAttribute('max'));
                    if (!isNaN(max) && value > max) {
                        value = max;
                        this.value = max;
                    }

                    self.state.quantity = value;
                });

                // Increase quantity button
                if (els.quantityIncBtn) {
                    els.quantityIncBtn.addEventListener('click', function () {
                        let currentVal = parseInt(els.quantityInput.value);
                        const max = parseInt(els.quantityInput.getAttribute('max'));

                        if (!isNaN(currentVal)) {
                            if (isNaN(max) || currentVal < max) {
                                els.quantityInput.value = currentVal + 1;
                                els.quantityInput.dispatchEvent(new Event('change'));
                            }
                        } else {
                            els.quantityInput.value = 1;
                            els.quantityInput.dispatchEvent(new Event('change'));
                        }
                    });
                }

                // Decrease quantity button
                if (els.quantityDecBtn) {
                    els.quantityDecBtn.addEventListener('click', function () {
                        let currentVal = parseInt(els.quantityInput.value);

                        if (!isNaN(currentVal) && currentVal > 1) {
                            els.quantityInput.value = currentVal - 1;
                            els.quantityInput.dispatchEvent(new Event('change'));
                        } else {
                            els.quantityInput.value = 1;
                            els.quantityInput.dispatchEvent(new Event('change'));
                        }
                    });
                }
            }

            // Wishlist button
            if (els.wishlistBtn) {
                // Check if product is already in wishlist and update button state
                const productId = els.wishlistBtn.getAttribute('data-product-id');
                if (self.state.wishlist.includes(productId)) {
                    els.wishlistBtn.classList.add('active');
                }

                els.wishlistBtn.addEventListener('click', function () {
                    const productId = this.getAttribute('data-product-id');
                    const productName = this.getAttribute('data-product-name');

                    // Toggle wishlist state
                    if (self.state.wishlist.includes(productId)) {
                        // Remove from wishlist
                        self.state.wishlist = self.state.wishlist.filter(id => id !== productId);
                        this.classList.remove('active');
                        self.showToast(`${productName} removed from wishlist`, 'info');
                    } else {
                        // Add to wishlist
                        self.state.wishlist.push(productId);
                        this.classList.add('active');
                        this.classList.add('animate-pulse');

                        // Remove animation after a delay
                        setTimeout(() => {
                            this.classList.remove('animate-pulse');
                        }, 700);

                        self.showToast(`${productName} added to wishlist`, 'success');
                    }

                    // Save updated wishlist to localStorage
                    localStorage.setItem('wishlist', JSON.stringify(self.state.wishlist));
                });
            }

            // Share button
            if (els.shareBtn) {
                els.shareBtn.addEventListener('click', function () {
                    const productName = this.getAttribute('data-product-name');
                    const pageUrl = window.location.href;

                    // If Web Share API is available, use it
                    if (navigator.share) {
                        navigator.share({
                            title: productName,
                            text: `Check out this product: ${productName}`,
                            url: pageUrl
                        })
                            .then(() => {
                                self.showToast('Product shared successfully!', 'success');
                            })
                            .catch(error => {
                                console.error('Error sharing:', error);
                            });
                    } else {
                        // Fallback to clipboard copy
                        navigator.clipboard.writeText(pageUrl)
                            .then(() => {
                                self.showToast('Link copied to clipboard!', 'success');
                            })
                            .catch(err => {
                                console.error('Failed to copy:', err);

                                // Ultimate fallback: show link in an alert
                                prompt('Copy this link to share:', pageUrl);
                            });
                    }
                });
            }

            // Color options
            if (els.colorOptions) {
                els.colorOptions.forEach(option => {
                    option.addEventListener('click', function () {
                        // Remove active class from all options
                        els.colorOptions.forEach(o => o.classList.remove('active'));

                        // Add active class to clicked option
                        this.classList.add('active');

                        // Update selected color
                        self.state.selectedColor = this.getAttribute('data-color');

                        // If there's a display element for the selected color, update it
                        const colorDisplay = document.querySelector('.selected-color-display');
                        if (colorDisplay) {
                            colorDisplay.textContent = self.state.selectedColor;
                        }
                    });
                });
            }

            // Size options
            if (els.sizeOptions) {
                els.sizeOptions.forEach(option => {
                    option.addEventListener('click', function () {
                        // Check if size is available
                        if (this.classList.contains('disabled')) {
                            self.showToast('This size is currently out of stock', 'warning');
                            return;
                        }

                        // Remove active class from all options
                        els.sizeOptions.forEach(o => o.classList.remove('active'));

                        // Add active class to clicked option
                        this.classList.add('active');

                        // Update selected size
                        self.state.selectedSize = this.getAttribute('data-size');

                        // If there's a display element for the selected size, update it
                        const sizeDisplay = document.querySelector('.selected-size-display');
                        if (sizeDisplay) {
                            sizeDisplay.textContent = self.state.selectedSize;
                        }
                    });
                });
            }

            // Add product to recently viewed
            const productDetailContainer = document.querySelector('.product-detail-container');
            if (productDetailContainer) {
                const productId = productDetailContainer.getAttribute('data-product-id');
                if (productId) {
                    // Get product details
                    const productDetails = {
                        id: productId,
                        name: document.querySelector('.product-title').textContent,
                        price: parseFloat(document.querySelector('.product-price').getAttribute('data-price')),
                        image: document.querySelector('.product-main-image img').getAttribute('src'),
                        brand: document.querySelector('.product-brand').textContent,
                        url: window.location.href
                    };

                    // Add to recently viewed (if not already first in the list)
                    if (self.state.recentlyViewed.length === 0 || self.state.recentlyViewed[0].id !== productId) {
                        // Remove product if it's already in the list
                        self.state.recentlyViewed = self.state.recentlyViewed.filter(item => item.id !== productId);

                        // Add product to the beginning of the list
                        self.state.recentlyViewed.unshift(productDetails);

                        // Limit the list to 10 items
                        if (self.state.recentlyViewed.length > 10) {
                            self.state.recentlyViewed = self.state.recentlyViewed.slice(0, 10);
                        }

                        // Save updated list to localStorage
                        localStorage.setItem('recentlyViewed', JSON.stringify(self.state.recentlyViewed));
                    }
                }
            }
        },

        // Initialize filters from URL parameters
        handleUrlParams: function () {
            const urlParams = new URLSearchParams(window.location.search);

            // Get category from URL
            const category = urlParams.get('category');
            if (category) {
                this.state.currentCategory = category;

                // Mark the corresponding category tag as active
                const categoryTag = document.querySelector(`.category-tag[data-category="${category}"]`);
                if (categoryTag) {
                    categoryTag.classList.add('active');
                }
            }

            // Get search query from URL
            const search = urlParams.get('search');
            if (search) {
                this.state.searchQuery = search.toLowerCase();

                // Set search input value
                if (this.elements.searchInput) {
                    this.elements.searchInput.value = search;
                }
            }

            // Get sort option from URL
            const sort = urlParams.get('sort');
            if (sort) {
                this.state.sortBy = sort;

                // Set the corresponding sort option as checked
                const sortOption = document.querySelector(`input[name="sort"][value="${sort}"]`);
                if (sortOption) {
                    sortOption.checked = true;
                }
            }

            // Get price range from URL
            const minPrice = urlParams.get('min_price');
            const maxPrice = urlParams.get('max_price');

            if (minPrice) {
                this.state.filters.priceRange.min = parseInt(minPrice);
                if (this.elements.priceRangeMin) {
                    this.elements.priceRangeMin.value = minPrice;
                }
            }

            if (maxPrice) {
                this.state.filters.priceRange.max = parseInt(maxPrice);
                if (this.elements.priceRangeMax) {
                    this.elements.priceRangeMax.value = maxPrice;
                }
            }
        },

        // Initialize filter values and states
        initializeFilters: function () {
            // Initialize price range sliders if using noUiSlider
            const priceRangeSlider = document.getElementById('price-range-slider');
            if (priceRangeSlider && window.noUiSlider) {
                noUiSlider.create(priceRangeSlider, {
                    start: [this.state.filters.priceRange.min, this.state.filters.priceRange.max],
                    connect: true,
                    step: 100,
                    range: {
                        'min': 0,
                        'max': 100000
                    },
                    format: {
                        to: function (value) {
                            return Math.round(value);
                        },
                        from: function (value) {
                            return Number(value);
                        }
                    }
                });

                // Update price range inputs when slider changes
                priceRangeSlider.noUiSlider.on('update', (values, handle) => {
                    const priceDisplay = document.getElementById('price-display');
                    if (priceDisplay) {
                        priceDisplay.textContent = `₹${values[0]} - ₹${values[1]}`;
                    }

                    if (handle === 0) {
                        if (this.elements.priceRangeMin) {
                            this.elements.priceRangeMin.value = values[0];
                        }
                        this.state.filters.priceRange.min = parseInt(values[0]);
                    } else {
                        if (this.elements.priceRangeMax) {
                            this.elements.priceRangeMax.value = values[1];
                        }
                        this.state.filters.priceRange.max = parseInt(values[1]);
                    }
                });

                // Filter products when slider stops changing
                priceRangeSlider.noUiSlider.on('change', this.debounce(() => {
                    this.filterProducts();
                }, 300));
            }

            // Initialize filter checkboxes
            document.querySelectorAll('.filter-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', () => {
                    const filterType = checkbox.getAttribute('data-filter-type');
                    const filterValue = checkbox.getAttribute('data-filter-value');

                    if (filterType === 'color') {
                        if (checkbox.checked) {
                            this.state.filters.colors.push(filterValue);
                        } else {
                            this.state.filters.colors = this.state.filters.colors.filter(c => c !== filterValue);
                        }
                    } else if (filterType === 'size') {
                        if (checkbox.checked) {
                            this.state.filters.sizes.push(filterValue);
                        } else {
                            this.state.filters.sizes = this.state.filters.sizes.filter(s => s !== filterValue);
                        }
                    } else if (filterType === 'inStock') {
                        this.state.filters.inStock = checkbox.checked;
                    }

                    this.filterProducts();
                });
            });
        },

        // Initialize animations for the products page
        initAnimations: function () {
            // Product cards entrance animation
            const productCards = document.querySelectorAll('.product-card');
            if (productCards.length > 0) {
                // If the Intersection Observer API is available
                if ('IntersectionObserver' in window) {
                    const options = {
                        root: null,
                        rootMargin: '0px',
                        threshold: 0.1
                    };

                    const observer = new IntersectionObserver((entries, observer) => {
                        entries.forEach(entry => {
                            if (entry.isIntersecting) {
                                const card = entry.target;
                                // Get the data-index or use the index from the array
                                const index = card.getAttribute('data-index') || Array.from(productCards).indexOf(card);

                                // Stagger the animations
                                setTimeout(() => {
                                    card.classList.add('animate-fade-in');
                                }, index * 100);

                                // Stop observing after animation is added
                                observer.unobserve(card);
                            }
                        });
                    }, options);

                    // Start observing cards
                    productCards.forEach(card => {
                        observer.observe(card);
                    });
                } else {
                    // Fallback for browsers that don't support Intersection Observer
                    productCards.forEach((card, index) => {
                        setTimeout(() => {
                            card.classList.add('animate-fade-in');
                        }, index * 100);
                    });
                }
            }
        },

        // Filter products based on current state
        filterProducts: function () {
            if (!this.elements.productsGrid || !document.body.classList.contains('js-filter-enabled')) {
                return;
            }

            const productCards = this.elements.productsGrid.querySelectorAll('.product-card');
            let visibleCount = 0;

            productCards.forEach(card => {
                const category = card.getAttribute('data-category') || '';
                const productName = card.getAttribute('data-name') || '';
                const productBrand = card.getAttribute('data-brand') || '';
                const productDescription = card.getAttribute('data-description') || '';
                const productPrice = parseFloat(card.getAttribute('data-price') || 0);
                const productColors = (card.getAttribute('data-colors') || '').split(',');
                const productSizes = (card.getAttribute('data-sizes') || '').split(',');
                const inStock = card.getAttribute('data-in-stock') === 'true';

                // Check if product passes all filters
                const passesCategory = !this.state.currentCategory || category.toLowerCase() === this.state.currentCategory.toLowerCase();
                const passesSearch = !this.state.searchQuery ||
                    productName.toLowerCase().includes(this.state.searchQuery) ||
                    productBrand.toLowerCase().includes(this.state.searchQuery) ||
                    productDescription.toLowerCase().includes(this.state.searchQuery);
                const passesPriceRange = productPrice >= this.state.filters.priceRange.min &&
                    productPrice <= this.state.filters.priceRange.max;
                const passesColors = this.state.filters.colors.length === 0 ||
                    this.state.filters.colors.some(color => productColors.includes(color));
                const passesSizes = this.state.filters.sizes.length === 0 ||
                    this.state.filters.sizes.some(size => productSizes.includes(size));
                const passesInStock = !this.state.filters.inStock || inStock;

                // Show or hide the product card
                if (passesCategory && passesSearch && passesPriceRange && passesColors && passesSizes && passesInStock) {
                    card.style.display = '';
                    visibleCount++;

                    // Animate card entrance
                    card.classList.add('animate-fade-in');
                } else {
                    card.style.display = 'none';
                    card.classList.remove('animate-fade-in');
                }
            });

            // Show "no products" message if no products are visible
            const noProductsMessage = document.querySelector('.no-products');
            if (noProductsMessage) {
                if (visibleCount === 0) {
                    noProductsMessage.style.display = 'block';
                } else {
                    noProductsMessage.style.display = 'none';
                }
            }

            // Update filter counts
            this.updateFilterCounts();

            // After filtering, sort products again
            this.sortProducts();
        },

        // Sort products based on current sort option
        sortProducts: function () {
            if (!this.elements.productsGrid || !document.body.classList.contains('js-filter-enabled')) {
                return;
            }

            const productsGrid = this.elements.productsGrid;
            const productCards = Array.from(productsGrid.querySelectorAll('.product-card'));

            // Only sort visible products
            const visibleProducts = productCards.filter(card => card.style.display !== 'none');

            // Sort products according to selected sort option
            visibleProducts.sort((a, b) => {
                switch (this.state.sortBy) {
                    case 'price-asc':
                        return parseFloat(a.getAttribute('data-price')) - parseFloat(b.getAttribute('data-price'));
                    case 'price-desc':
                        return parseFloat(b.getAttribute('data-price')) - parseFloat(a.getAttribute('data-price'));
                    case 'newest':
                        return new Date(b.getAttribute('data-date')) - new Date(a.getAttribute('data-date'));
                    case 'oldest':
                        return new Date(a.getAttribute('data-date')) - new Date(b.getAttribute('data-date'));
                    case 'name-asc':
                        return a.getAttribute('data-name').localeCompare(b.getAttribute('data-name'));
                    case 'name-desc':
                        return b.getAttribute('data-name').localeCompare(a.getAttribute('data-name'));
                    default:
                        return 0;
                }
            });

            // Re-append sorted cards to maintain order
            visibleProducts.forEach(card => {
                productsGrid.appendChild(card);
            });
        },

        // Update filter option count displays
        updateFilterCounts: function () {
            document.querySelectorAll('.filter-count').forEach(countElem => {
                const filterType = countElem.getAttribute('data-filter-type');
                const filterValue = countElem.getAttribute('data-filter-value');

                if (!filterType || !filterValue) return;

                // Count products that match this filter
                let count = 0;
                const productCards = this.elements.productsGrid.querySelectorAll('.product-card');

                productCards.forEach(card => {
                    // Skip products that are filtered out by other criteria
                    if (card.style.display === 'none') return;

                    // Check if product matches this filter
                    if (filterType === 'category') {
                        const category = card.getAttribute('data-category') || '';
                        if (category.toLowerCase() === filterValue.toLowerCase()) {
                            count++;
                        }
                    } else if (filterType === 'color') {
                        const colors = (card.getAttribute('data-colors') || '').split(',');
                        if (colors.includes(filterValue)) {
                            count++;
                        }
                    } else if (filterType === 'size') {
                        const sizes = (card.getAttribute('data-sizes') || '').split(',');
                        if (sizes.includes(filterValue)) {
                            count++;
                        }
                    }
                });

                // Update count display
                countElem.textContent = `(${count})`;
            });
        },

        // Open quick view modal for a product
        openQuickView: function (productId) {
            const self = this;

            // Show loading overlay
            const loadingOverlay = document.getElementById('loading-overlay');
            if (loadingOverlay) {
                loadingOverlay.style.display = 'flex';
            }

            // Fetch product data (in a real app, this would be an AJAX call)
            setTimeout(() => {
                // For demo, we'll get data from the DOM
                const productCard = document.querySelector(`.product-card[data-product-id="${productId}"]`);

                if (productCard) {
                    const productName = productCard.getAttribute('data-name');
                    const productBrand = productCard.getAttribute('data-brand');
                    const productPrice = productCard.getAttribute('data-price');
                    const productImage = productCard.querySelector('.product-image img').getAttribute('src');
                    const productDesc = productCard.getAttribute('data-description');

                    // Create and show quick view modal
                    const quickViewHtml = `
                        <div class="modal quick-view-modal" id="quickViewModal">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h2 class="modal-title">${productName}</h2>
                                    <button class="modal-close" id="closeQuickView">&times;</button>
                                </div>
                                <div class="modal-body">
                                    <div class="quick-view-grid">
                                        <div class="quick-view-image">
                                            <img src="${productImage}" alt="${productName}">
                                        </div>
                                        <div class="quick-view-details">
                                            <p class="product-brand">${productBrand}</p>
                                            <p class="product-price">₹${parseFloat(productPrice).toFixed(2)}</p>
                                            <div class="product-description">
                                                <p>${productDesc}</p>
                                            </div>
                                            <div class="quick-view-actions">
                                                <button class="btn btn-primary add-to-cart-btn" 
                                                    data-product-id="${productId}"
                                                    data-product-name="${productName}"
                                                    data-product-price="${productPrice}"
                                                    data-product-image="${productImage}"
                                                    data-product-brand="${productBrand}">
                                                    <i class="fas fa-shopping-cart"></i> Add to Cart
                                                </button>
                                                <a href="/products/${productId}" class="btn btn-secondary">
                                                    View Details
                                                </a>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;

                    // Add modal to the DOM
                    const modalContainer = document.createElement('div');
                    modalContainer.innerHTML = quickViewHtml;
                    document.body.appendChild(modalContainer.firstChild);

                    // Show modal
                    const quickViewModal = document.getElementById('quickViewModal');
                    quickViewModal.classList.add('show');

                    // Add event listeners
                    const closeBtn = document.getElementById('closeQuickView');
                    closeBtn.addEventListener('click', () => {
                        quickViewModal.classList.remove('show');
                        setTimeout(() => {
                            quickViewModal.remove();
                        }, 300);
                    });

                    // Add to cart button in quick view
                    const addToCartBtn = quickViewModal.querySelector('.add-to-cart-btn');
                    addToCartBtn.addEventListener('click', function () {
                        // Add animation to the button
                        this.classList.add('animate-pulse');

                        // Add to cart logic
                        if (typeof FashionCoreCart !== 'undefined') {
                            const cart = new FashionCoreCart();
                            cart.addToCart({
                                id: productId,
                                name: productName,
                                price: parseFloat(productPrice),
                                image: productImage,
                                brand: productBrand,
                                quantity: 1
                            });
                        } else {
                            // Fallback to basic localStorage implementation
                            self.addToCart({
                                id: productId,
                                name: productName,
                                price: parseFloat(productPrice),
                                image: productImage,
                                brand: productBrand,
                                quantity: 1
                            });
                        }

                        // Reset button animation after a delay
                        setTimeout(() => {
                            this.classList.remove('animate-pulse');
                        }, 700);

                        // Show success message
                        self.showToast(`${productName} added to cart!`, 'success');
                    });

                    // Close modal when clicking outside
                    quickViewModal.addEventListener('click', (e) => {
                        if (e.target === quickViewModal) {
                            quickViewModal.classList.remove('show');
                            setTimeout(() => {
                                quickViewModal.remove();
                            }, 300);
                        }
                    });
                }

                // Hide loading overlay
                if (loadingOverlay) {
                    loadingOverlay.style.display = 'none';
                }
            }, 800); // Simulating network delay
        },

        // Basic cart functionality (fallback if cart.js is not available)
        addToCart: function (item) {
            // Get cart items from localStorage
            let cartItems = JSON.parse(localStorage.getItem('cartItems')) || [];

            // Check if item already exists
            const existingItemIndex = cartItems.findIndex(i => i.id === item.id);

            if (existingItemIndex > -1) {
                // Update quantity if item exists
                cartItems[existingItemIndex].quantity += item.quantity;
            } else {
                // Add new item
                cartItems.push(item);
            }

            // Save updated cart
            localStorage.setItem('cartItems', JSON.stringify(cartItems));

            // Update cart count in header
            const cartCountElement = document.getElementById('cart-count');
            if (cartCountElement) {
                cartCountElement.textContent = cartItems.length;
            }
        },

        // Show toast notification
        showToast: function (message, type = 'info') {
            // Check if toast container exists, create if not
            let toastContainer = document.querySelector('.toast-container');
            if (!toastContainer) {
                toastContainer = document.createElement('div');
                toastContainer.className = 'toast-container';
                document.body.appendChild(toastContainer);
            }

            // Create toast element
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;

            // Set icon based on type
            let icon = 'info-circle';
            if (type === 'success') icon = 'check-circle';
            if (type === 'error') icon = 'times-circle';
            if (type === 'warning') icon = 'exclamation-triangle';

            // Create toast content
            toast.innerHTML = `
                <div class="toast-icon"><i class="fas fa-${icon}"></i></div>
                <div class="toast-content">
                    <div class="toast-message">${message}</div>
                </div>
                <button class="toast-close">&times;</button>
                <div class="toast-progress"></div>
            `;

            // Add toast to container
            toastContainer.appendChild(toast);

            // Add close event to toast
            const closeBtn = toast.querySelector('.toast-close');
            closeBtn.addEventListener('click', () => {
                toast.classList.add('animate-fade-out');
                setTimeout(() => {
                    toast.remove();
                }, 300);
            });

            // Auto-remove toast after 5 seconds
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.classList.add('animate-fade-out');
                    setTimeout(() => {
                        toast.remove();
                    }, 300);
                }
            }, 5000);
        },

        // Debounce function for performance optimization
        debounce: function (func, wait) {
            let timeout;
            return function () {
                const context = this;
                const args = arguments;
                clearTimeout(timeout);
                timeout = setTimeout(() => {
                    func.apply(context, args);
                }, wait);
            };
        }
    };

    // Initialize the Products controller
    ProductsController.init();
});