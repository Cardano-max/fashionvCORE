/**
 * fashionCORE Try-On JavaScript for Kling AI implementation
 * 
 * This script handles the virtual try-on functionality using Kling AI API, including:
 * - Image uploads (person and garment)
 * - Image cropping and editing
 * - Try-on generation and display
 * - Result sharing
 * - Error handling and connection retries
 */

// Main Try-On class
class FashionCoreKlingTryOn {
    constructor(options = {}) {
        // Default settings
        this.settings = {
            apiEndpoint: '/api/try-on-kling',
            personUploadAreaId: 'personUploadArea',
            personBrowseBtnId: 'personBrowseBtn',
            personImageInputId: 'personImageInput',
            personPreviewContainerId: 'personPreviewContainer',
            personPreviewId: 'personPreview',
            personEditBtnId: 'personEditBtn',
            personRemoveBtnId: 'personRemoveBtn',
            
            garmentUploadAreaId: 'garmentUploadArea',
            garmentBrowseBtnId: 'garmentBrowseBtn',
            garmentImageInputId: 'garmentImageInput',
            garmentPreviewContainerId: 'garmentPreviewContainer',
            garmentPreviewId: 'garmentPreview',
            garmentEditBtnId: 'garmentEditBtn',
            garmentRemoveBtnId: 'garmentRemoveBtn',
            
            generateBtnId: 'generateBtn',
            statusMessageId: 'statusMessage',
            statusIndicatorId: 'statusIndicator',
            statusDotId: 'statusDot',
            statusTextId: 'statusText',
            resultSectionId: 'resultSection',
            resultImageId: 'resultImage',
            originalPersonContainerId: 'originalPersonContainer',
            downloadBtnId: 'downloadBtn',
            shareBtnId: 'shareBtn',
            tryAgainBtnId: 'tryAgainBtn',
            
            cropperModalId: 'cropperModal',
            closeModalId: 'closeModal',
            cropperImageId: 'cropperImage',
            cropCancelBtnId: 'cropCancelBtn',
            cropApplyBtnId: 'cropApplyBtn',
            
            shareModalId: 'shareModal',
            closeShareModalId: 'closeShareModal',
            shareLinkId: 'shareLink',
            copyLinkBtnId: 'copyLinkBtn',
            
            loadingOverlayId: 'loadingOverlay',
            loadingMessageId: 'loadingMessage',
            loadingSubMessageId: 'loadingSubMessage',
            progressBarId: 'progressBar',
            errorMessageId: 'error-message',
            connectionStatusId: 'connectionStatus',
            
            productIdField: 'productId',
            
            maxRetries: 3,
            retryDelay: 2000,
            
            onSuccess: null,
            onError: null,
            onUploaded: null
        };
        
        // Merge options with default settings
        Object.assign(this.settings, options);
        
        // Initialize state
        this.state = {
            personImage: null,
            garmentImage: null,
            currentEditingImage: null,
            cropper: null,
            resultUrl: null,
            retryCount: 0,
            apiRequestInProgress: false,
            progressValue: 0,
            progressInterval: null
        };
        
        // Initialize elements
        this.elements = {};
        
        // Initialize the try-on functionality
        this.init();
    }
    
    /**
     * Initialize the try-on functionality
     */
    init() {
        // Get DOM elements
        this.getElements();
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Check if a garment product is pre-selected
        this.checkForPreselectedProduct();
    }
    
    /**
     * Get DOM elements
     */
    getElements() {
        const s = this.settings;
        const e = this.elements;
        
        // Person upload elements
        e.personUploadArea = document.getElementById(s.personUploadAreaId);
        e.personBrowseBtn = document.getElementById(s.personBrowseBtnId);
        e.personImageInput = document.getElementById(s.personImageInputId);
        e.personPreviewContainer = document.getElementById(s.personPreviewContainerId);
        e.personPreview = document.getElementById(s.personPreviewId);
        e.personEditBtn = document.getElementById(s.personEditBtnId);
        e.personRemoveBtn = document.getElementById(s.personRemoveBtnId);
        
        // Garment upload elements
        e.garmentUploadArea = document.getElementById(s.garmentUploadAreaId);
        e.garmentBrowseBtn = document.getElementById(s.garmentBrowseBtnId);
        e.garmentImageInput = document.getElementById(s.garmentImageInputId);
        e.garmentPreviewContainer = document.getElementById(s.garmentPreviewContainerId) || document.getElementById('selectedGarmentContainer');
        e.garmentPreview = document.getElementById(s.garmentPreviewId);
        e.garmentEditBtn = document.getElementById(s.garmentEditBtnId);
        e.garmentRemoveBtn = document.getElementById(s.garmentRemoveBtnId);
        
        // Action elements
        e.generateBtn = document.getElementById(s.generateBtnId);
        e.statusMessage = document.getElementById(s.statusMessageId);
        e.statusIndicator = document.getElementById(s.statusIndicatorId);
        e.statusDot = document.getElementById(s.statusDotId);
        e.statusText = document.getElementById(s.statusTextId);
        e.resultSection = document.getElementById(s.resultSectionId);
        e.resultImage = document.getElementById(s.resultImageId);
        e.originalPersonContainer = document.getElementById(s.originalPersonContainerId);
        e.downloadBtn = document.getElementById(s.downloadBtnId);
        e.shareBtn = document.getElementById(s.shareBtnId);
        e.tryAgainBtn = document.getElementById(s.tryAgainBtnId);
        
        // Cropper modal elements
        e.cropperModal = document.getElementById(s.cropperModalId);
        e.closeModal = document.getElementById(s.closeModalId);
        e.cropperImage = document.getElementById(s.cropperImageId);
        e.cropCancelBtn = document.getElementById(s.cropCancelBtnId);
        e.cropApplyBtn = document.getElementById(s.cropApplyBtnId);
        
        // Share modal elements
        e.shareModal = document.getElementById(s.shareModalId);
        e.closeShareModal = document.getElementById(s.closeShareModalId);
        e.shareLink = document.getElementById(s.shareLinkId);
        e.copyLinkBtn = document.getElementById(s.copyLinkBtnId);
        
        // Loading and error elements
        e.loadingOverlay = document.getElementById(s.loadingOverlayId);
        e.loadingMessage = document.getElementById(s.loadingMessageId);
        e.loadingSubMessage = document.getElementById(s.loadingSubMessageId);
        e.progressBar = document.getElementById(s.progressBarId);
        e.errorMessage = document.getElementById(s.errorMessageId);
        e.connectionStatus = document.getElementById(s.connectionStatusId);
        
        // Product ID field (if applicable)
        e.productIdField = document.getElementById(s.productIdField);
    }
    
    /**
     * Set up event listeners
     */
    setupEventListeners() {
        // Setup person upload
        this.setupUpload(
            this.elements.personUploadArea,
            this.elements.personBrowseBtn,
            this.elements.personImageInput,
            this.elements.personPreviewContainer,
            this.elements.personPreview,
            this.elements.personEditBtn,
            this.elements.personRemoveBtn,
            'person'
        );
        
        // Setup garment upload
        this.setupUpload(
            this.elements.garmentUploadArea,
            this.elements.garmentBrowseBtn,
            this.elements.garmentImageInput,
            this.elements.garmentPreviewContainer,
            this.elements.garmentPreview,
            this.elements.garmentEditBtn,
            this.elements.garmentRemoveBtn,
            'garment'
        );
        
        // Generate button
        if (this.elements.generateBtn) {
            this.elements.generateBtn.addEventListener('click', () => this.generateTryOn());
        }
        
        // Cropper modal
        if (this.elements.closeModal) {
            this.elements.closeModal.addEventListener('click', () => this.closeCropperModal());
        }
        
        if (this.elements.cropCancelBtn) {
            this.elements.cropCancelBtn.addEventListener('click', () => this.closeCropperModal());
        }
        
        if (this.elements.cropApplyBtn) {
            this.elements.cropApplyBtn.addEventListener('click', () => this.applyCrop());
        }
        
        // Result actions
        if (this.elements.downloadBtn) {
            this.elements.downloadBtn.addEventListener('click', () => this.downloadResult());
        }
        
        if (this.elements.shareBtn) {
            this.elements.shareBtn.addEventListener('click', () => this.openShareModal());
        }
        
        if (this.elements.tryAgainBtn) {
            this.elements.tryAgainBtn.addEventListener('click', () => this.resetTryOn());
        }
        
        // Share modal
        if (this.elements.closeShareModal) {
            this.elements.closeShareModal.addEventListener('click', () => this.closeShareModal());
        }
        
        if (this.elements.copyLinkBtn) {
            this.elements.copyLinkBtn.addEventListener('click', () => this.copyShareLink());
        }
        
        // Setup share options
        this.setupShareOptions();
        
        // Close modals when clicking outside
        window.addEventListener('click', (e) => {
            if (e.target === this.elements.cropperModal) {
                this.closeCropperModal();
            }
            if (e.target === this.elements.shareModal) {
                this.closeShareModal();
            }
        });
    }
    
    /**
     * Setup upload for person or garment
     */
    setupUpload(uploadArea, browseBtn, input, previewContainer, preview, editBtn, removeBtn, imageType) {
        // Click to browse
        if (browseBtn && input) {
            browseBtn.addEventListener('click', () => {
                input.click();
            });
        }
        
        // Drag and drop
        if (uploadArea) {
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });
            
            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('dragover');
            });
            
            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                if (e.dataTransfer.files.length > 0) {
                    this.handleImageUpload(e.dataTransfer.files[0], imageType);
                }
            });
        }
        
        // File input change
        if (input) {
            input.addEventListener('change', () => {
                if (input.files.length > 0) {
                    this.handleImageUpload(input.files[0], imageType);
                }
            });
        }
        
        // Edit button
        if (editBtn) {
            editBtn.addEventListener('click', () => {
                this.openCropperModal(imageType);
            });
        }
        
        // Remove button
        if (removeBtn) {
            removeBtn.addEventListener('click', () => {
                this.removeImage(imageType);
            });
        }
    }
    
    /**
     * Check if a garment product is pre-selected
     */
    checkForPreselectedProduct() {
        if (document.getElementById('selectedGarmentContainer')) {
            const garmentImg = this.elements.garmentPreview.querySelector('img');
            if (garmentImg) {
                // Convert the pre-selected product image to a File object
                fetch(garmentImg.src)
                    .then(res => res.blob())
                    .then(blob => {
                        this.state.garmentImage = new File([blob], "product-garment.jpg", { type: "image/jpeg" });
                        this.checkCanGenerate();
                    })
                    .catch(error => {
                        console.error("Error converting image to File:", error);
                    });
            }
        }
    }
    
    /**
     * Handle image upload
     */
    handleImageUpload(file, imageType) {
        if (!file.type.match('image.*')) {
            this.showStatus('Please upload an image file', 'error');
            return;
        }
        
        // Check file size
        const maxSize = 10 * 1024 * 1024; // 10MB
        if (file.size > maxSize) {
            this.showStatus('Image file is too large. Please upload an image smaller than 10MB.', 'error');
            return;
        }
        
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                // Check image dimensions
                if (img.width < 300 || img.height < 300) {
                    this.showStatus('Image is too small. Please upload an image with at least 300x300 pixels.', 'error');
                    return;
                }
                
                if (imageType === 'person') {
                    this.state.personImage = file;
                    this.elements.personPreview.innerHTML = '';
                    const previewImg = document.createElement('img');
                    previewImg.src = e.target.result;
                    previewImg.alt = 'Person preview';
                    this.elements.personPreview.appendChild(previewImg);
                    this.elements.personPreviewContainer.style.display = 'block';
                    if (this.elements.personUploadArea) {
                        this.elements.personUploadArea.style.display = 'none';
                    }
                } else {
                    this.state.garmentImage = file;
                    this.elements.garmentPreview.innerHTML = '';
                    const previewImg = document.createElement('img');
                    previewImg.src = e.target.result;
                    previewImg.alt = 'Garment preview';
                    this.elements.garmentPreview.appendChild(previewImg);
                    this.elements.garmentPreviewContainer.style.display = 'block';
                    if (this.elements.garmentUploadArea) {
                        this.elements.garmentUploadArea.style.display = 'none';
                    }
                }
                
                this.checkCanGenerate();
                
                // Call the onUploaded callback if provided
                if (this.settings.onUploaded) {
                    this.settings.onUploaded(imageType, file);
                }
            };
            img.src = e.target.result;
        };
        reader.readAsDataURL(file);
    }
    
    /**
     * Open cropper modal
     */
    openCropperModal(imageType) {
        this.state.currentEditingImage = imageType;
        
        const imgSrc = imageType === 'person' 
            ? this.elements.personPreview.querySelector('img').src 
            : this.elements.garmentPreview.querySelector('img').src;
        
        this.elements.cropperImage.src = imgSrc;
        this.elements.cropperModal.style.display = 'block';
        document.body.classList.add('modal-open');
        
        // Initialize cropper
        if (this.state.cropper) {
            this.state.cropper.destroy();
        }
        
        // Make sure Cropper.js is available
        if (typeof Cropper !== 'undefined') {
            this.state.cropper = new Cropper(this.elements.cropperImage, {
                aspectRatio: NaN,
                viewMode: 1,
                autoCropArea: 0.8,
                zoomable: true,
                scalable: true,
                rotatable: true
            });
        } else {
            console.error('Cropper.js is not loaded. Make sure to include it in your page.');
        }
    }
    
    /**
     * Close cropper modal
     */
    closeCropperModal() {
        this.elements.cropperModal.style.display = 'none';
        document.body.classList.remove('modal-open');
        if (this.state.cropper) {
            this.state.cropper.destroy();
            this.state.cropper = null;
        }
    }
    
    /**
     * Apply crop
     */
    applyCrop() {
        if (!this.state.cropper) return;
        
        const canvas = this.state.cropper.getCroppedCanvas({
            maxWidth: 1024,
            maxHeight: 1024
        });
        
        if (canvas) {
            const dataUrl = canvas.toDataURL('image/jpeg');
            
            // Convert data URL to File object
            fetch(dataUrl)
                .then(res => res.blob())
                .then(blob => {
                    const file = new File([blob], "cropped-image.jpg", { type: "image/jpeg" });
                    
                    if (this.state.currentEditingImage === 'person') {
                        this.state.personImage = file;
                        this.elements.personPreview.innerHTML = '';
                        const previewImg = document.createElement('img');
                        previewImg.src = dataUrl;
                        this.elements.personPreview.appendChild(previewImg);
                    } else {
                        this.state.garmentImage = file;
                        this.elements.garmentPreview.innerHTML = '';
                        const previewImg = document.createElement('img');
                        previewImg.src = dataUrl;
                        this.elements.garmentPreview.appendChild(previewImg);
                    }
                    
                    // Call the onUploaded callback if provided
                    if (this.settings.onUploaded) {
                        this.settings.onUploaded(this.state.currentEditingImage, file);
                    }
                });
        }
        
        this.closeCropperModal();
    }
    
    /**
     * Remove image
     */
    removeImage(imageType) {
        if (imageType === 'person') {
            this.state.personImage = null;
            this.elements.personPreviewContainer.style.display = 'none';
            if (this.elements.personUploadArea) {
                this.elements.personUploadArea.style.display = 'flex';
            }
        } else {
            this.state.garmentImage = null;
            this.elements.garmentPreviewContainer.style.display = 'none';
            if (this.elements.garmentUploadArea) {
                this.elements.garmentUploadArea.style.display = 'flex';
            }
        }
        
        this.checkCanGenerate();
    }
    
    /**
     * Check if try-on can be generated
     */
    checkCanGenerate() {
        if (!this.elements.generateBtn) return;
        
        this.elements.generateBtn.disabled = !(this.state.personImage && this.state.garmentImage);
        
        if (this.state.personImage && this.state.garmentImage) {
            this.elements.generateBtn.classList.add('active');
        } else {
            this.elements.generateBtn.classList.remove('active');
        }
    }
    
    /**
     * Start progress animation
     */
    startProgressAnimation() {
        if (this.elements.progressBar) {
            this.state.progressValue = 0;
            this.elements.progressBar.style.width = '0%';
            
            // Clear any existing interval
            if (this.state.progressInterval) {
                clearInterval(this.state.progressInterval);
            }
            
            // Create a new interval that increases progress gradually
            this.state.progressInterval = setInterval(() => {
                // Progress should move quickly to 70%, then slow down
                if (this.state.progressValue < 70) {
                    this.state.progressValue += 1;
                } else {
                    // Random small increments after 70%
                    this.state.progressValue += Math.random() * 0.3;
                }
                
                // Cap at 95% - we'll jump to 100% when complete
                if (this.state.progressValue > 95) {
                    this.state.progressValue = 95;
                    clearInterval(this.state.progressInterval);
                }
                
                this.elements.progressBar.style.width = this.state.progressValue + '%';
            }, 200);
        }
    }
    
    /**
     * Complete progress animation
     */
    completeProgressAnimation() {
        if (this.elements.progressBar) {
            // Clear interval if it exists
            if (this.state.progressInterval) {
                clearInterval(this.state.progressInterval);
                this.state.progressInterval = null;
            }
            
            // Set to 100%
            this.state.progressValue = 100;
            this.elements.progressBar.style.width = '100%';
            
            // Add a small delay before hiding the loading overlay
            setTimeout(() => {
                if (this.elements.loadingOverlay) {
                    this.elements.loadingOverlay.style.display = 'none';
                }
            }, 500);
        }
    }
    
    /**
     * Update status indicator
     */
    updateStatusIndicator(status, message) {
        if (!this.elements.statusIndicator || !this.elements.statusDot || !this.elements.statusText) {
            return;
        }
        
        // Show the status indicator
        this.elements.statusIndicator.style.display = 'flex';
        
        // Update text
        this.elements.statusText.textContent = message || 'Processing...';
        
        // Update dot status
        this.elements.statusDot.className = 'status-dot ' + status;
    }
    
    /**
     * Show connection status
     */
    showConnectionStatus(show) {
        if (this.elements.connectionStatus) {
            this.elements.connectionStatus.style.display = show ? 'block' : 'none';
        }
    }
    
    /**
     * Generate try-on using Kling AI API
     */
    generateTryOn(isRetry = false) {
        if (!this.state.personImage || !this.state.garmentImage) return;
        
        // Prevent multiple submissions
        if (this.state.apiRequestInProgress) {
            return;
        }
        
        this.state.apiRequestInProgress = true;
        
        if (this.elements.loadingOverlay) {
            this.elements.loadingOverlay.style.display = 'flex';
        }
        
        if (this.elements.loadingMessage) {
            this.elements.loadingMessage.textContent = 'Processing your images...';
        }
        
        if (this.elements.loadingSubMessage) {
            this.elements.loadingSubMessage.textContent = 'This may take up to 2 minutes';
        }
        
        // If this is a retry, show connection status indicator
        if (isRetry) {
            this.showConnectionStatus(true);
        } else {
            this.showConnectionStatus(false);
        }
        
        // Update status indicator
        this.updateStatusIndicator('processing', 'Processing your try-on request...');
        
        // Start progress animation
        this.startProgressAnimation();
        
        // Save person image for comparison
        if (this.state.personImage && this.elements.originalPersonContainer) {
            const reader = new FileReader();
            reader.onload = (e) => {
                this.elements.originalPersonContainer.innerHTML = '';
                const img = document.createElement('img');
                img.src = e.target.result;
                img.alt = 'Original person';
                this.elements.originalPersonContainer.appendChild(img);
            };
            reader.readAsDataURL(this.state.personImage);
        }
        
        // Create form data
        const formData = new FormData();
        formData.append('person_image', this.state.personImage);
        formData.append('garment_image', this.state.garmentImage);
        
        // Add product ID if available
        if (this.elements.productIdField) {
            formData.append('product_id', this.elements.productIdField.value);
        }
        
        // Send API request
        fetch(this.settings.apiEndpoint, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.message || `Server responded with ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            this.state.apiRequestInProgress = false;
            this.state.retryCount = 0;
            this.showConnectionStatus(false);
            
            if (data.status === 'success') {
                this.state.resultUrl = data.result_url;
                
                // Complete progress animation
                this.completeProgressAnimation();
                
                if (this.elements.resultImage) {
                    this.elements.resultImage.src = data.result_url;
                }
                
                if (this.elements.resultSection) {
                    this.elements.resultSection.style.display = 'block';
                }
                
                // Set share link
                if (this.elements.shareLink) {
                    this.elements.shareLink.value = window.location.origin + data.result_url;
                }
                
                // Scroll to result
                if (this.elements.resultSection) {
                    this.elements.resultSection.scrollIntoView({ behavior: 'smooth' });
                }
                
                // Update status indicator
                this.updateStatusIndicator('success', 'Try-on successful!');
                
                // Update credits display if authenticated
                const creditsDisplay = document.querySelector('.free-trial-info .highlight');
                if (creditsDisplay) {
                    const currentCredits = parseInt(creditsDisplay.textContent);
                    if (!isNaN(currentCredits)) {
                        creditsDisplay.textContent = currentCredits - 1;
                    }
                }
                
                // Call the onSuccess callback if provided
                if (this.settings.onSuccess) {
                    this.settings.onSuccess(data);
                }
            } else {
                // Error during image processing
                this.completeProgressAnimation();
                this.updateStatusIndicator('error', 'Processing failed');
                this.showError('Error: ' + (data.message || 'Failed to process images'));
                
                // Call the onError callback if provided
                if (this.settings.onError) {
                    this.settings.onError(data);
                }
            }
        })
        .catch(error => {
            console.error("API Error:", error);
            this.state.apiRequestInProgress = false;
            
            // Handle retry logic
            if (this.state.retryCount < this.settings.maxRetries) {
                this.state.retryCount++;
                console.log(`Retry attempt ${this.state.retryCount}/${this.settings.maxRetries}...`);
                
                // Show retry in progress
                if (this.elements.loadingSubMessage) {
                    this.elements.loadingSubMessage.textContent = `Connection issue. Retrying (${this.state.retryCount}/${this.settings.maxRetries})...`;
                }
                
                // Wait and retry
                setTimeout(() => {
                    this.generateTryOn(true);
                }, this.settings.retryDelay);
                
                return;
            }
            
            // If we've exhausted retries, show error
            this.completeProgressAnimation();
            this.showConnectionStatus(false);
            this.updateStatusIndicator('error', 'Connection failed');
            
            this.showError('Error: ' + error.message + ' Please try again later.');
            
            // Call the onError callback if provided
            if (this.settings.onError) {
                this.settings.onError({ status: 'error', message: error.message });
            }
        });
    }
    
    /**
     * Show status message
     */
    showStatus(message, type = 'info') {
        if (!this.elements.statusMessage) return;
        
        this.elements.statusMessage.textContent = message;
        this.elements.statusMessage.className = 'status-message ' + type;
        
        // Clear after 5 seconds
        setTimeout(() => {
            this.elements.statusMessage.textContent = '';
            this.elements.statusMessage.className = 'status-message';
        }, 5000);
    }
    
    /**
     * Show error message
     */
    showError(message) {
        if (!this.elements.errorMessage) return;
        
        this.elements.errorMessage.textContent = message;
        this.elements.errorMessage.style.display = 'block';
        
        // Clear after 5 seconds
        setTimeout(() => {
            this.elements.errorMessage.style.display = 'none';
        }, 5000);
    }
    
    /**
     * Download result
     */
    downloadResult() {
        if (!this.state.resultUrl) return;
        
        const link = document.createElement('a');
        link.href = this.state.resultUrl;
        link.download = 'fashionCORE-virtual-try-on.png';
        link.click();
    }
    
    /**
     * Open share modal
     */
    openShareModal() {
        if (!this.elements.shareModal) return;
        
        this.elements.shareModal.style.display = 'block';
        document.body.classList.add('modal-open');
    }
    
    /**
     * Close share modal
     */
    closeShareModal() {
        if (!this.elements.shareModal) return;
        
        this.elements.shareModal.style.display = 'none';
        document.body.classList.remove('modal-open');
    }
    
    /**
     * Copy share link
     */
    copyShareLink() {
        if (!this.elements.shareLink) return;
        
        this.elements.shareLink.select();
        document.execCommand('copy');
        
        if (this.elements.copyLinkBtn) {
            this.elements.copyLinkBtn.textContent = 'Copied!';
            setTimeout(() => {
                this.elements.copyLinkBtn.textContent = 'Copy';
            }, 2000);
        }
    }
    
    /**
     * Setup share options
     */
    setupShareOptions() {
        const shareOptions = document.querySelectorAll('.share-option');
        
        shareOptions.forEach(option => {
            option.addEventListener('click', () => {
                if (!this.elements.shareLink) return;
                
                const url = encodeURIComponent(this.elements.shareLink.value);
                const resultUrl = this.state.resultUrl;
                let shareUrl = '';
                
                if (option.classList.contains('facebook')) {
                    shareUrl = `https://www.facebook.com/sharer/sharer.php?u=${url}`;
                } else if (option.classList.contains('twitter')) {
                    shareUrl = `https://twitter.com/intent/tweet?url=${url}&text=${encodeURIComponent('Check out my virtual try-on with fashionCORE!')}`;
                } else if (option.classList.contains('instagram')) {
                    // Show message about Instagram
                    alert('To share on Instagram, please download the image and upload it to your Instagram account.');
                    return;
                } else if (option.classList.contains('whatsapp')) {
                    shareUrl = `https://wa.me/?text=${encodeURIComponent('Check out my virtual try-on with fashionCORE! ' + this.elements.shareLink.value)}`;
                }
                
                if (shareUrl) {
                    window.open(shareUrl, '_blank');
                }
            });
        });
    }
    
    /**
     * Reset try-on
     */
    resetTryOn() {
        if (this.elements.resultSection) {
            this.elements.resultSection.style.display = 'none';
        }
        
        // Hide status indicator
        if (this.elements.statusIndicator) {
            this.elements.statusIndicator.style.display = 'none';
        }
        
        const tryOnSection = document.getElementById('try-on-section');
        if (tryOnSection) {
            tryOnSection.scrollIntoView({ behavior: 'smooth' });
        }
    }
}

// Export the FashionCoreKlingTryOn class
if (typeof module !== 'undefined' && typeof module.exports !== 'undefined') {
    module.exports = FashionCoreKlingTryOn;
} else {
    window.FashionCoreKlingTryOn = FashionCoreKlingTryOn;
}

// Initialize the try-on functionality when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Check if try-on elements exist on the page
    if (document.getElementById('personUploadArea') || document.getElementById('garmentUploadArea')) {
        // Initialize the try-on functionality with default settings
        new FashionCoreKlingTryOn();
    }
});