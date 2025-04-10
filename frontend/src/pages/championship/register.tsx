import React, { useState } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import Link from 'next/link';
import axios from 'axios';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import styles from '../../../styles/Championship.module.css';

// API URL
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const ChampionshipRegistration: React.FC = () => {
  const router = useRouter();
  
  // Form state
  const [teamName, setTeamName] = useState('');
  const [apiEndpoint, setApiEndpoint] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validation
    if (!teamName.trim()) {
      setError('Team Name is required');
      return;
    }
    
    if (!apiEndpoint.trim()) {
      setError('API Endpoint is required');
      return;
    }
    
    setError(null);
    setIsSubmitting(true);
    
    try {
      // Check if the API endpoint already has the connect4-move path
      let endpoint = apiEndpoint.trim();
      if (!endpoint.includes('/api/connect4-move')) {
        // If URL ends with /, remove it before adding the endpoint
        if (endpoint.endsWith('/')) {
          endpoint = endpoint.slice(0, -1);
        }
        endpoint = `${endpoint}/api/connect4-move`;
      }
      
      // Submit registration
      const response = await axios.post(`${API_URL}/api/championship/register`, {
        team_name: teamName.trim(),
        api_endpoint: endpoint
      });
      
      toast.success(response.data.message);
      
      // Redirect to dashboard after successful registration
      setTimeout(() => {
        router.push('/championship/dashboard');
      }, 2000);
    } catch (error) {
      console.error('Registration error:', error);
      if (axios.isAxiosError(error) && error.response) {
        setError(error.response.data.detail || 'Registration failed. Please try again.');
        toast.error(error.response.data.detail || 'Registration failed');
      } else {
        setError('Network error. Please check your connection and try again.');
        toast.error('Network error. Please check your connection');
      }
      setIsSubmitting(false);
    }
  };
  
  return (
    <>
      <Head>
        <title>Join Championship - Connect 4</title>
        <meta name="description" content="Register your AI for the Connect 4 Championship" />
      </Head>
      
      <div className={styles.container}>
        <h1 className={styles.title}>Championship Registration</h1>
        
        <div className={styles.infoBox}>
          <h2>How it works</h2>
          <p>Register your AI to participate in a round-robin tournament against other AIs.</p>
          <ul>
            <li>Each team will play against every other team in a round-robin format.</li>
            <li>Each match consists of 4 games, alternating which team goes first.</li>
            <li>Your AI endpoint must accept POST requests with game state and return a valid move.</li>
            <li>The championship will start automatically when 19 teams are registered.</li>
          </ul>
        </div>
        
        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.formGroup}>
            <label htmlFor="teamName">Team Name</label>
            <input
              type="text"
              id="teamName"
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              placeholder="Enter your team name"
              className={styles.input}
              disabled={isSubmitting}
            />
          </div>
          
          <div className={styles.formGroup}>
            <label htmlFor="apiEndpoint">API Endpoint</label>
            <input
              type="text"
              id="apiEndpoint"
              value={apiEndpoint}
              onChange={(e) => setApiEndpoint(e.target.value)}
              placeholder="https://your-ai-endpoint.com"
              className={styles.input}
              disabled={isSubmitting}
            />
            <p className={styles.hint}>
              We'll automatically append <code>/api/connect4-move</code> if needed
            </p>
          </div>
          
          {error && <div className={styles.error}>{error}</div>}
          
          <div className={styles.apiFormat}>
            <h3>API Format</h3>
            <p>Your endpoint must accept POST requests with the following JSON:</p>
            <pre className={styles.codeBlock}>
{`{
  "board": [[0,0,0,...], [...], ...],  // 6x7 board state
  "current_player": 1,                 // 1 or 2
  "valid_moves": [0,1,2,...]           // Available column indices
}`}
            </pre>
            
            <p>And return a JSON response with your move (column index):</p>
            <pre className={styles.codeBlock}>
{`{
  "move": 3  // Column index (0-6)
}`}
            </pre>
          </div>
          
          <div className={styles.actions}>
            <button
              type="submit"
              className={styles.submitButton}
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Registering...' : 'Register Team'}
            </button>
            
            <Link href="/" className={styles.cancelLink}>
              Cancel
            </Link>
          </div>
        </form>
        
        <div className={styles.navigation}>
          <Link href="/championship/dashboard" className={styles.navLink}>
            View Championship Dashboard
          </Link>
        </div>
      </div>
      
      <ToastContainer position="bottom-right" autoClose={3000} />
    </>
  );
};

export default ChampionshipRegistration; 