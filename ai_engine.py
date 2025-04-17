from transformers import pipeline

# Load a summarization pipeline (this might download the model the first time it is run)
summarizer = pipeline("summarization", model="t5-small")

def summarize_text(text, max_length=150, min_length=40):
    # The summarization pipeline can automatically handle various parameters
    summary_list = summarizer(text, max_length=max_length, min_length=min_length, do_sample=False)
    return summary_list[0]['summary_text']

if __name__ == "__main__":
    sample_text = (
        "Artificial Intelligence (AI) is transforming the way we work and live. "
        "From automating mundane tasks to enabling innovative solutions in complex domains, "
        "AI is evolving at a rapid pace."
    )
    summary = summarize_text(sample_text)
    print("Summary:", summary)
