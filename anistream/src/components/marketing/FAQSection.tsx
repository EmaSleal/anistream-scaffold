import styles from "./FAQSection.module.css";

interface FAQItem {
  question: string;
  answer: string;
}

const FAQS: FAQItem[] = [
  {
    question: "Is Anistream really free?",
    answer: "Yes, completely free. No hidden fees, no credit card required. Watch as much as you want at no cost.",
  },
  {
    question: "Do I need an account?",
    answer: "You need to sign in with Google to track your watchlist and progress. Browsing is free and available to everyone.",
  },
  {
    question: "Is it available in my country?",
    answer: "Anistream is available worldwide. We don't geo-restrict content.",
  },
  {
    question: "What quality is the video?",
    answer: "We stream in HD. Quality adapts automatically to your internet connection for the smoothest experience.",
  },
  {
    question: "How often is new content added?",
    answer: "New simulcast episodes land within hours of the Japan broadcast. Classic titles are added regularly too.",
  },
  {
    question: "Can I watch offline?",
    answer: "Not yet — offline downloads are on our roadmap. For now, you need an internet connection to stream.",
  },
];

export function FAQSection() {
  return (
    <section id="faq" className={styles.section}>
      <div className={styles.container}>
        <h2 className={styles.heading}>Frequently asked questions</h2>
        <div className={styles.list}>
          {FAQS.map((faq) => (
            <details key={faq.question} className={styles.item}>
              <summary className={styles.summary}>
                <span className={styles.question}>{faq.question}</span>
                <svg
                  className={styles.chevron}
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </summary>
              <p className={styles.answer}>{faq.answer}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
