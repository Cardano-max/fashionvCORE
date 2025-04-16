/**
 * tryontrend Business Try-On JavaScript
 * 
 * This script handles the business-focused virtual try-on functionality, including:
 * - Model selection
 * - Pose selection
 * - Background selection
 * - Garment image upload
 * - Try-on generation and display
 * - Result sharing
 */

// Main Business Try-On class
class FashionCoreBusinessTryOn {
    constructor(options = {}) {
        // Default settings
        this.settings = {
            apiEndpoint: '/api/business-try-on',
            modelGridId: 'modelGrid',
            poseSelectorId: 'poseSelector',
            backgroundSelectorId: 'backgroundSelector',

            garmentUploadAreaId: 'garmentUploadArea',
            garmentBrowseBtnId: 'garmentBrowseBtn',
            garmentImageInputId: 'garmentImageInput',
            garmentPreviewContainerId: 'garmentPreviewContainer',
            garmentPreviewId: 'garmentPreview',
            garmentRemoveBtnId: 'garmentRemoveBtn',

            generateBtnId: 'generateBtn',
            statusMessageId: 'statusMessage',
            resultSectionId: 'resultSection',
            resultImageId: 'resultImage',
            downloadBtnId: 'downloadBtn',
            shareBtnId: 'shareBtn',
            tryAgainBtnId: 'tryAgainBtn',

            shareModalId: 'shareModal',
            closeShareModalId: 'closeShareModal',
            shareLinkId: 'shareLink',
            copyLinkBtnId: 'copyLinkBtn',

            loadingOverlayId: 'loadingOverlay',
            loadingMessageId: 'loadingMessage',
            loadingSubMessageId: 'loadingSubMessage',

            onSuccess: null,
            onError: null
        };

        // Merge options with default settings
        Object.assign(this.settings, options);

        // Initialize state
        this.state = {
            selectedModel: null,
            selectedPose: null,
            selectedBackground: null,
            garmentImage: null,
            resultUrl: null
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
    }

    /**
     * Get DOM elements
     */
    getElements() {
        const s = this.settings;
        const e = this.elements;

        // Selection elements
        e.modelGrid = document.getElementById(s.modelGridId);
        e.poseSelector = document.getElementById(s.poseSelectorId);
        e.backgroundSelector = document.getElementById(s.backgroundSelectorId);

        // Garment upload elements
        e.garmentUploadArea = document.getElementById(s.garmentUploadAreaId);
        e.garmentBrowseBtn = document.getElementById(s.garmentBrowseBtnId);
        e.garmentImageInput = document.getElementById(s.garmentImageInputId);
        e.garmentPreviewContainer = document.getElementById(s.garmentPreviewContainerId);
        e.garmentPreview = document.getElementById(s.garmentPreviewId);
        e.garmentRemoveBtn = document.getElementById(s.garmentRemoveBtnId);

        // Action elements
        e.generateBtn = document.getElementById(s.generateBtnId);
        e.statusMessage = document.getElementById(s.statusMessageId);
        e.resultSection = document.getElementById(s.resultSectionId);
        e.resultImage = document.getElementById(s.resultImageId);
        e.downloadBtn = document.getElementById(s.downloadBtnId);
        e.shareBtn = document.getElementById(s.shareBtnId);
        e.tryAgainBtn = document.getElementById(s.tryAgainBtnId);

        // Share modal elements
        e.shareModal = document.getElementById(s.shareModalId);
        e.closeShareModal = document.getElementById(s.closeShareModalId);
        e.shareLink = document.getElementById(s.shareLinkId);
        e.copyLinkBtn = document.getElementById(s.copyLinkBtnId);

        // Loading elements
        e.loadingOverlay = document.getElementById(s.loadingOverlayId);
        e.loadingMessage = document.getElementById(s.loadingMessageId);
        e.loadingSubMessage = document.getElementById(s.loadingSubMessageId);
    }

    /**
     * Set up event listeners
     */
    setupEventListeners() {
        // Model selection
        if (this.elements.modelGrid) {
            const modelCards = this.elements.modelGrid.querySelectorAll('.model-card');
            modelCards.forEach(card => {
                card.addEventListener('click', () => {
                    this.selectModel(card);
                });
            });
        }

        // Pose selection
        if (this.elements.poseSelector) {
            const poseOptions = this.elements.poseSelector.querySelectorAll('.pose-option');
            poseOptions.forEach(option => {
                option.addEventListener('click', () => {
                    this.selectPose(option);
                });
            });
        }

        // Background selection
        if (this.elements.backgroundSelector) {
            const bgOptions = this.elements.backgroundSelector.querySelectorAll('.bg-option');
            bgOptions.forEach(option => {
                option.addEventListener('click', () => {
                    this.selectBackground(option);
                });
            });
        }

        // Setup garment upload
        this.setupGarmentUpload();

        // Generate button
        if (this.elements.generateBtn) {
            this.elements.generateBtn.addEventListener('click', () => {
                this.generateTryOn();
            });
        }

        // Result actions
        if (this.elements.downloadBtn) {
            this.elements.downloadBtn.addEventListener('click', () => {
                this.downloadResult();
            });
        }

        if (this.elements.shareBtn) {
            this.elements.shareBtn.addEventListener('click', () => {
                this.openShareModal();
            });
        }

        if (this.elements.tryAgainBtn) {
            this.elements.tryAgainBtn.addEventListener('click', () => {
                this.resetToGenerator();
            });
        }

        // Share modal
        if (this.elements.closeShareModal) {
            this.elements.closeShareModal.addEventListener('click', () => {
                this.closeShareModal();
            });
        }

        if (this.elements.copyLinkBtn) {
            this.elements.copyLinkBtn.addEventListener('click', () => {
                this.copyShareLink();
            });
        }

        // Setup share options
        this.setupShareOptions();

        // Close modals when clicking outside
        window.addEventListener('click', (e) => {
            if (e.target === this.elements.shareModal) {
                this.closeShareModal();
            }
        });
    }

    /**
     * Select a model
     */
    selectModel(modelCard) {
        // Remove active class from all model cards
        const modelCards = this.elements.modelGrid.querySelectorAll('.model-card');
        modelCards.forEach(card => {
            card.classList.remove('selected');
        });

        // Add active class to selected model card
        modelCard.classList.add('selected');

        // Update state
        this.state.selectedModel = modelCard.getAttribute('data-model-id');

        // Check if can generate
        this.checkCanGenerate();
    }

    /**
     * Select a pose
     */
    selectPose(poseOption) {
        // Remove active class from all pose options
        const poseOptions = this.elements.poseSelector.querySelectorAll('.pose-option');
        poseOptions.forEach(option => {
            option.classList.remove('selected');
        });

        // Add active class to selected pose option
        poseOption.classList.add('selected');

        // Update state
        this.state.selectedPose = poseOption.getAttribute('data-pose-id');

        // Check if can generate
        this.checkCanGenerate();
    }

    /**
     * Select a background
     */
    selectBackground(bgOption) {
        // Remove active class from all background options
        const bgOptions = this.elements.backgroundSelector.querySelectorAll('.bg-option');
        bgOptions.forEach(option => {
            option.classList.remove('selected');
        });

        // Add active class to selected background option
        bgOption.classList.add('selected');

        // Update state
        this.state.selectedBackground = {
            id: bgOption.getAttribute('data-bg-id'),
            type: bgOption.getAttribute('data-bg-type'),
            value: bgOption.getAttribute('data-bg-value')
        };

        // Check if can generate
        this.checkCanGenerate();
    }

    /**
     * Setup garment upload functionality
     */
    setupGarmentUpload() {
        // Click to browse
        if (this.elements.garmentBrowseBtn && this.elements.garmentImageInput) {
            this.elements.garmentBrowseBtn.addEventListener('click', () => {
                this.elements.garmentImageInput.click();
            });
        }

        // Drag and drop
        if (this.elements.garmentUploadArea) {
            this.elements.garmentUploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                this.elements.garmentUploadArea.classList.add('dragover');
            });

            this.elements.garmentUploadArea.addEventListener('dragleave', () => {
                this.elements.garmentUploadArea.classList.remove('dragover');
            });

            this.elements.garmentUploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                this.elements.garmentUploadArea.classList.remove('dragover');
                if (e.dataTransfer.files.length > 0) {
                    this.handleGarmentUpload(e.dataTransfer.files[0]);
                }
            });
        }

        // File input change
        if (this.elements.garmentImageInput) {
            this.elements.garmentImageInput.addEventListener('change', () => {
                if (this.elements.garmentImageInput.files.length > 0) {
                    this.handleGarmentUpload(this.elements.garmentImageInput.files[0]);
                }
            });
        }

        // Remove button
        if (this.elements.garmentRemoveBtn) {
            this.elements.garmentRemoveBtn.addEventListener('click', () => {
                this.removeGarmentImage();
            });
        }
    }

    /**
     * Handle garment image upload
     */
    handleGarmentUpload(file) {
        if (!file.type.match('image.*')) {
            this.showStatus('Please upload an image file', 'error');
            return;
        }

        // Check if user is authenticated
        fetch('/api/check-auth')
            .then(response => response.json())
            .then(data => {
                if (!data.authenticated) {
                    // Show sign-in popup
                    this.showSignInPopup();
                    return;
                }

                // User is authenticated, proceed with upload
                const reader = new FileReader();
                reader.onload = (e) => {
                    const img = new Image();
                    img.onload = () => {
                        this.state.garmentImage = file;
                        this.elements.garmentPreview.innerHTML = '';
                        const previewImg = document.createElement('img');
                        previewImg.src = e.target.result;
                        previewImg.alt = 'Garment preview';
                        this.elements.garmentPreview.appendChild(previewImg);
                        this.elements.garmentPreviewContainer.style.display = 'block';
                        this.elements.garmentUploadArea.style.display = 'none';

                        this.checkCanGenerate();
                    };
                    img.src = e.target.result;
                };
                reader.readAsDataURL(file);
            })
            .catch(error => {
                console.error('Error checking authentication:', error);
                this.showStatus('Error checking authentication', 'error');
            });
    }

    /**
     * Show sign-in popup
     */
    showSignInPopup() {
        const popup = document.createElement('div');
        popup.className = 'auth-popup';
        popup.innerHTML = `
            <div class="auth-popup-content">
                <h3>Sign In Required</h3>
                <p>Please sign in to upload garment images and use the virtual try-on feature.</p>
                <div class="auth-popup-buttons">
                    <button class="btn btn-primary" onclick="window.location.href='/login'">Sign In</button>
                    <button class="btn btn-secondary" onclick="this.closest('.auth-popup').remove()">Cancel</button>
                </div>
            </div>
        `;

        document.body.appendChild(popup);
    }

    /**
     * Remove garment image
     */
    removeGarmentImage() {
        this.state.garmentImage = null;
        this.elements.garmentPreviewContainer.style.display = 'none';
        this.elements.garmentUploadArea.style.display = 'flex';
        this.elements.garmentImageInput.value = '';

        this.checkCanGenerate();
    }

    /**
     * Check if try-on can be generated
     */
    checkCanGenerate() {
        const canGenerate = (
            this.state.selectedModel !== null &&
            this.state.selectedPose !== null &&
            this.state.selectedBackground !== null &&
            this.state.garmentImage !== null
        );

        if (this.elements.generateBtn) {
            this.elements.generateBtn.disabled = !canGenerate;

            if (canGenerate) {
                this.elements.generateBtn.classList.add('active');
            } else {
                this.elements.generateBtn.classList.remove('active');
            }
        }

        return canGenerate;
    }

    /**
     * Generate try-on image
     */
    generateTryOn() {
        if (!this.checkCanGenerate()) {
            this.showStatus('Please complete all steps before generating', 'error');
            return;
        }

        // Show loading overlay
        if (this.elements.loadingOverlay) {
            this.elements.loadingOverlay.style.display = 'flex';
        }

        // Create form data
        const formData = new FormData();
        formData.append('model_id', this.state.selectedModel);
        formData.append('pose_id', this.state.selectedPose);
        formData.append('background_type', this.state.selectedBackground.type);
        formData.append('background_value', this.state.selectedBackground.value);
        formData.append('garment_image', this.state.garmentImage);

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
                // Hide loading overlay
                if (this.elements.loadingOverlay) {
                    this.elements.loadingOverlay.style.display = 'none';
                }

                if (data.status === 'success') {
                    this.state.resultUrl = data.result_url;

                    // Update result image
                    if (this.elements.resultImage) {
                        this.elements.resultImage.src = data.result_url;
                    }

                    // Update download button
                    if (this.elements.downloadBtn) {
                        this.elements.downloadBtn.href = data.result_url;
                    }

                    // Show result section
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

                    this.showStatus('Your professional image has been generated successfully!', 'success');

                    // Call the onSuccess callback if provided
                    if (this.settings.onSuccess) {
                        this.settings.onSuccess(data);
                    }
                } else {
                    this.showStatus('Error: ' + (data.message || 'Failed to generate image'), 'error');

                    // Call the onError callback if provided
                    if (this.settings.onError) {
                        this.settings.onError(data);
                    }
                }
            })
            .catch(error => {
                console.error("API Error:", error);

                // Hide loading overlay
                if (this.elements.loadingOverlay) {
                    this.elements.loadingOverlay.style.display = 'none';
                }

                this.showStatus('Error: ' + error.message, 'error');

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
     * Download result
     */
    downloadResult() {
        // This is handled automatically by the href attribute of the download button
    }

    /**
     * Reset to generator view
     */
    resetToGenerator() {
        if (this.elements.resultSection) {
            this.elements.resultSection.style.display = 'none';
        }

        // Scroll to try-on section
        const tryOnSection = document.getElementById('business-try-on');
        if (tryOnSection) {
            tryOnSection.scrollIntoView({ behavior: 'smooth' });
        }
    }

    /**
     * Open share modal
     */
    openShareModal() {
        if (!this.elements.shareModal) return;

        this.elements.shareModal.style.display = 'block';
    }

    /**
     * Close share modal
     */
    closeShareModal() {
        if (!this.elements.shareModal) return;

        this.elements.shareModal.style.display = 'none';
    }

    /**
     * Copy share link
     */
    copyShareLink() {
        if (!this.elements.shareLink) return;

        this.elements.shareLink.select();
        document.execCommand('copy');

        if (this.elements.copyLinkBtn) {
            const originalText = this.elements.copyLinkBtn.textContent;
            this.elements.copyLinkBtn.textContent = 'Copied!';
            setTimeout(() => {
                this.elements.copyLinkBtn.textContent = originalText;
            }, 2000);
        }
    }

    /**
     * Setup share options
     */
    setupShareOptions() {
        const shareButtons = document.querySelectorAll('.social-share-btn');

        shareButtons.forEach(button => {
            button.addEventListener('click', () => {
                if (!this.elements.shareLink || !this.state.resultUrl) return;

                const url = encodeURIComponent(this.elements.shareLink.value);
                const title = encodeURIComponent('Check out my professional product image created with tryontrend!');
                let shareUrl = '';

                if (button.classList.contains('facebook')) {
                    shareUrl = `https://www.facebook.com/sharer/sharer.php?u=${url}`;
                } else if (button.classList.contains('twitter')) {
                    shareUrl = `https://twitter.com/intent/tweet?url=${url}&text=${title}`;
                } else if (button.classList.contains('pinterest')) {
                    shareUrl = `https://pinterest.com/pin/create/button/?url=${url}&media=${encodeURIComponent(this.state.resultUrl)}&description=${title}`;
                } else if (button.classList.contains('linkedin')) {
                    shareUrl = `https://www.linkedin.com/sharing/share-offsite/?url=${url}`;
                }

                if (shareUrl) {
                    window.open(shareUrl, '_blank');
                }
            });
        });
    }
}

// Initialize the business try-on functionality when the DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    // Initialize the business try-on functionality with default settings
    window.businessTryOn = new FashionCoreBusinessTryOn();
});