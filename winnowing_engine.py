import hashlib

def get_kgrams(text, k):
    """Step 1 & 2: Clean text and generate overlapping k-grams."""
    # Remove all non-alphanumeric characters and lowercase
    clean_text = ''.join(char for char in text if char.isalnum()).lower()
    return [clean_text[i:i+k] for i in range(len(clean_text) - k + 1)]

def hash_string(string):
    """Step 3: Convert the k-gram into an integer hash."""
    # Using MD5 and converting the first 8 hex characters to an integer
    return int(hashlib.md5(string.encode('utf-8')).hexdigest()[:8], 16)

def generate_fingerprints(text, k=10, w=5):
    """Step 4: The Winnowing process."""
    kgrams = get_kgrams(text, k)
    hashes = [hash_string(kg) for kg in kgrams]
    
    fingerprints = set()
    
    # Slide a window of size W across the hashes
    for i in range(len(hashes) - w + 1):
        window = hashes[i:i+w]
        # The core of Winnowing: only keep the minimum hash in the window
        fingerprints.add(min(window))
        
    return fingerprints

# --- TESTING THE ENGINE ---

original_essay = "The rapid development of artificial intelligence has changed the world entirely."
copied_essay = "People say that the rapid development of artificial intelligence has changed things."

# Generate fingerprints
fingerprints_A = generate_fingerprints(original_essay)
fingerprints_B = generate_fingerprints(copied_essay)

# Find shared fingerprints (The mathematical intersection)
shared_hashes = fingerprints_A.intersection(fingerprints_B)
similarity_score = (len(shared_hashes) / min(len(fingerprints_A), len(fingerprints_B))) * 100

print(f"Original Fingerprint Count: {len(fingerprints_A)}")
print(f"Copied Fingerprint Count: {len(fingerprints_B)}")
print(f"Shared Fingerprints: {len(shared_hashes)}")
print(f"Calculated Similarity: {similarity_score:.2f}%")