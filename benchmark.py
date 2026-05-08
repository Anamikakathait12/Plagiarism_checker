import time
import difflib
import hashlib
import matplotlib.pyplot as plt

# 1. Simulate a dummy student essay (approx 300 words)
dummy_text = "The quick brown fox jumps over the lazy dog. " * 30 

def simulate_peer_to_peer_scan(num_students):
    """Simulates the N*(N-1)/2 comparisons using Gestalt Pattern Matching O(N^2)."""
    comparisons = 0
    for i in range(num_students):
        for j in range(i + 1, num_students):
            matcher = difflib.SequenceMatcher(None, dummy_text, dummy_text)
            ratio = matcher.ratio()
            comparisons += 1
    return comparisons

def simulate_global_scan(num_students):
    """Simulates Winnowing fingerprint generation and O(1) DB lookup per student."""
    db_lookups = 0
    # Simulating a massive database of existing historical hashes
    dummy_db_hashes = set(range(10000))
    
    for i in range(num_students):
        # Simulate slicing into K-grams and generating cryptographic hashes
        kgrams = [dummy_text[k:k+5] for k in range(len(dummy_text)-4)]
        hashes = set(int(hashlib.md5(kg.encode('utf-8')).hexdigest(), 16) % 20000 for kg in kgrams)
        
        # Simulate the O(1) mathematical intersection against the SQL database
        intersection = hashes.intersection(dummy_db_hashes)
        db_lookups += 1
        
    return db_lookups

# 2. The Benchmark Algorithm
student_batch_sizes = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
gestalt_times = []
winnowing_times = []

print("Running Dual-Layer Time Complexity Benchmark...")

for N in student_batch_sizes:
    # 1. Benchmark Peer-to-Peer (Gestalt)
    start_time = time.time()
    simulate_peer_to_peer_scan(N)
    gestalt_times.append(time.time() - start_time)
    
    # 2. Benchmark Global Scan (Winnowing)
    start_time = time.time()
    simulate_global_scan(N)
    winnowing_times.append(time.time() - start_time)
    
    print(f"Batch Size (N={N}) Processed.")

# 3. Plotting the Results
plt.figure(figsize=(10, 6))

# Plot both lines to show the contrast in efficiency
plt.plot(student_batch_sizes, gestalt_times, marker='o', linestyle='-', color='#dc3545', linewidth=2.5, label='Gestalt Peer-to-Peer $O(N^2)$')
plt.plot(student_batch_sizes, winnowing_times, marker='s', linestyle='-', color='#0d6efd', linewidth=2.5, label='Winnowing Global Scan $O(N)$')

# Formatting the graph for the research paper
plt.title('Time Complexity: Peer-to-Peer vs. Global Database Scan', fontweight='bold', fontsize=14)
plt.xlabel('Number of Student Documents Uploaded (N)', fontweight='bold')
plt.ylabel('Execution Time (Seconds)', fontweight='bold')
plt.grid(True, linestyle='--', alpha=0.7)
plt.legend(fontsize=12)

# Save the graph as a picture for your research paper!
plt.tight_layout()
plt.savefig("updated_time_complexity_graph.png", dpi=300)
print("✅ Success: Graph saved as updated_time_complexity_graph.png")
plt.show()