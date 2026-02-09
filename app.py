import os
import json
import csv
from io import StringIO
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import networkx as nx
from datetime import datetime

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

# Initialize the knowledge graph
kg = nx.DiGraph()

# Store metadata for nodes and edges
node_metadata = {}
edge_metadata = {}


def add_relationship(entity1, relationship, entity2):
    """Add a relationship between two entities to the knowledge graph."""
    if not entity1 or not entity2 or not relationship:
        return False, "All fields are required"
    
    entity1 = entity1.strip()
    entity2 = entity2.strip()
    relationship = relationship.strip()
    
    # Add nodes if they don't exist
    if entity1 not in kg:
        kg.add_node(entity1)
        node_metadata[entity1] = {
            'created_at': datetime.now().isoformat(),
            'type': 'entity'
        }
    
    if entity2 not in kg:
        kg.add_node(entity2)
        node_metadata[entity2] = {
            'created_at': datetime.now().isoformat(),
            'type': 'entity'
        }
    
    # Add edge with relationship as attribute
    kg.add_edge(entity1, entity2, label=relationship)
    edge_key = (entity1, entity2, relationship)
    edge_metadata[str(edge_key)] = {
        'created_at': datetime.now().isoformat()
    }
    
    return True, f"Relationship added: {entity1} --{relationship}--> {entity2}"


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'Knowledge Graph API is running'}), 200


@app.route('/api/relationships/add', methods=['POST'])
def add_single_relationship():
    """Add a single relationship to the knowledge graph."""
    try:
        data = request.get_json()
        entity1 = data.get('entity1')
        relationship = data.get('relationship')
        entity2 = data.get('entity2')
        
        success, message = add_relationship(entity1, relationship, entity2)
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'graph': get_graph_data()
            }), 201
        else:
            return jsonify({'success': False, 'message': message}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/relationships/bulk', methods=['POST'])
def bulk_upload():
    """Upload relationships from a CSV file."""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'message': 'Only CSV files are supported'}), 400
        
        # Read CSV file
        content = file.stream.read().decode('utf-8-sig')
        stream = StringIO(content)
        csv_reader = csv.DictReader(stream)
        
        # Normalize headers (strip whitespace and lower case)
        if csv_reader.fieldnames:
            csv_reader.fieldnames = [name.strip() for name in csv_reader.fieldnames]
        
        added_count = 0
        errors = []
        
        for row_num, row in enumerate(csv_reader, start=2):
            try:
                # robust extraction
                entity1 = row.get('Entity1') or row.get('entity1') or row.get('Entity 1') or row.get('entity 1')
                relationship = row.get('Relationship') or row.get('relationship')
                entity2 = row.get('Entity2') or row.get('entity2') or row.get('Entity 2') or row.get('entity 2')
                
                if not entity1 or not relationship or not entity2:
                    errors.append(f"Row {row_num}: Missing required fields (Found: {list(row.keys())})")
                    continue
                
                success, _ = add_relationship(entity1, relationship, entity2)
                if success:
                    added_count += 1
                else:
                    errors.append(f"Row {row_num}: Failed to add relationship")
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        return jsonify({
            'success': True,
            'added_count': added_count,
            'errors': errors,
            'graph': get_graph_data()
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/graph', methods=['GET'])
def get_graph():
    """Get the current knowledge graph structure."""
    return jsonify(get_graph_data()), 200


def get_graph_data():
    """Convert NetworkX graph to JSON format for visualization."""
    nodes = []
    edges = []
    
    # Add all nodes
    for node in kg.nodes():
        nodes.append({
            'id': node,
            'label': node,
            'metadata': node_metadata.get(node, {})
        })
    
    # Add all edges
    for source, target, data in kg.edges(data=True):
        edges.append({
            'source': source,
            'target': target,
            'label': data.get('label', 'related_to'),
            'metadata': edge_metadata.get(str((source, target, data.get('label', 'related_to'))), {})
        })
    
    return {
        'nodes': nodes,
        'edges': edges,
        'node_count': kg.number_of_nodes(),
        'edge_count': kg.number_of_edges()
    }


@app.route('/api/query', methods=['POST'])
def query_graph():
    """Query the knowledge graph."""
    try:
        data = request.get_json()
        query_type = data.get('type')
        query_value = data.get('value', '').strip()
        
        if not query_type or not query_value:
            return jsonify({'success': False, 'message': 'Query type and value are required'}), 400
        
        results = []
        
        if query_type == 'entity':
            # Find all relationships involving this entity
            if query_value in kg:
                # Outgoing relationships
                for target in kg.successors(query_value):
                    edge_data = kg.get_edge_data(query_value, target)
                    results.append({
                        'type': 'outgoing',
                        'source': query_value,
                        'relationship': edge_data.get('label', 'related_to'),
                        'target': target
                    })
                
                # Incoming relationships
                for source in kg.predecessors(query_value):
                    edge_data = kg.get_edge_data(source, query_value)
                    results.append({
                        'type': 'incoming',
                        'source': source,
                        'relationship': edge_data.get('label', 'related_to'),
                        'target': query_value
                    })
        
        elif query_type == 'relationship':
            # Find all edges with this relationship type
            for source, target, data in kg.edges(data=True):
                if data.get('label', '').lower() == query_value.lower():
                    results.append({
                        'source': source,
                        'relationship': data.get('label', 'related_to'),
                        'target': target
                    })
        
        elif query_type == 'path':
            # Find shortest path between two entities
            parts = query_value.split(' to ')
            if len(parts) == 2:
                start, end = parts[0].strip(), parts[1].strip()
                if start in kg and end in kg:
                    try:
                        path = nx.shortest_path(kg, start, end)
                        results = {
                            'path': path,
                            'length': len(path) - 1
                        }
                    except nx.NetworkXNoPath:
                        results = {'path': None, 'message': f'No path found between {start} and {end}'}
        
        return jsonify({
            'success': True,
            'query_type': query_type,
            'query_value': query_value,
            'results': results,
            'result_count': len(results) if isinstance(results, list) else 1
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/relationships/delete', methods=['DELETE'])
def delete_relationship():
    """Delete a relationship from the knowledge graph."""
    try:
        data = request.get_json()
        source = data.get('source')
        target = data.get('target')
        
        if source and target and source in kg and target in kg:
            kg.remove_edge(source, target)
            # Clean up isolated nodes if needed
            return jsonify({
                'success': True,
                'message': f'Relationship removed: {source} -> {target}',
                'graph': get_graph_data()
            }), 200
        else:
            return jsonify({'success': False, 'message': 'Invalid source or target'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/graph/clear', methods=['POST'])
def clear_graph():
    """Clear the entire knowledge graph."""
    try:
        kg.clear()
        node_metadata.clear()
        edge_metadata.clear()
        return jsonify({
            'success': True,
            'message': 'Knowledge graph cleared',
            'graph': get_graph_data()
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/graph/stats', methods=['GET'])
def get_stats():
    """Get statistics about the knowledge graph."""
    try:
        stats = {
            'node_count': kg.number_of_nodes(),
            'edge_count': kg.number_of_edges(),
            'density': nx.density(kg),
            'is_connected': nx.is_strongly_connected(kg) if kg.number_of_nodes() > 0 else False,
            'num_components': nx.number_strongly_connected_components(kg),
            'avg_degree': sum(dict(kg.degree()).values()) / kg.number_of_nodes() if kg.number_of_nodes() > 0 else 0
        }
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
