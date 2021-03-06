import torch
import numpy as np
from .text import text_to_sequence, phoneme_to_sequence


def text_to_seqvec(text, CONFIG, use_cuda):
    text_cleaner = [CONFIG.text_cleaner]
    # text ot phonemes to sequence vector
    if CONFIG.use_phonemes:
        seq = np.asarray(
            phoneme_to_sequence(text, text_cleaner, CONFIG.phoneme_language,
                                CONFIG.enable_eos_bos_chars),
            dtype=np.int32)
    else:
        seq = np.asarray(text_to_sequence(text, text_cleaner), dtype=np.int32)
    # torch tensor
    chars_var = torch.from_numpy(seq).unsqueeze(0)
    if use_cuda:
        chars_var = chars_var.cuda()
    return chars_var.long()


def compute_style_mel(style_wav, ap, use_cuda):
    print('>>>>>>>>>>>>>>>>>>style_wav')
    print(style_wav)
    #style_mel = torch.FloatTensor(ap.melspectrogram(ap.load_wav(style_wav)).astype('float32') ).unsqueeze(0)    
    wav=ap.load_wav(style_wav)
    
    #style_mel=np.asarray(wav, dtype=np.float32)
    style_mel = ap.melspectrogram(wav.astype('float32'))
        

    style_mel=torch.FloatTensor(style_mel).unsqueeze(0).contiguous()
    
    #style_mel = style_mel.transpose(0, 2, 1)
    #style_mel = ap.load_wav(style_wav).astype('float32')
    #style_mel = style_mel.transpose(0, 2, 1)
    #style_mel = torch.FloatTensor(style_mel).contiguous()


    if use_cuda:
        return style_mel.cuda()
    return style_mel


def run_model(model, inputs, CONFIG, truncated, speaker_id=None, style_mel=None,ref_cond=True):
    #if CONFIG.use_gst:
    if ref_cond:
        decoder_output, postnet_output, alignments, stop_tokens = model.inference(inputs, style_mel=style_mel, speaker_ids=speaker_id,ref_cond=True)
        print(postnet_output.shape)

        print('>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
        _, postnet_output_noRef, _, _ = model.inference(inputs, style_mel=style_mel, speaker_ids=speaker_id,ref_cond=False)
        print(postnet_output_noRef.shape)
    else:
        if truncated:
            decoder_output, postnet_output, alignments, stop_tokens = model.inference_truncated(
                inputs, speaker_ids=speaker_id)
        else:
            decoder_output, postnet_output, alignments, stop_tokens = model.inference(
                inputs, speaker_ids=speaker_id,ref_cond=ref_cond)
    return decoder_output, postnet_output,postnet_output_noRef, alignments, stop_tokens


def parse_outputs(postnet_output, decoder_output, alignments):
    postnet_output = postnet_output[0].data.cpu().numpy()
    decoder_output = decoder_output[0].data.cpu().numpy()
    alignment = alignments[0].cpu().data.numpy()
    return postnet_output, decoder_output, alignment


def trim_silence(wav, ap):
    return wav[:ap.find_endpoint(wav)]


def inv_spectrogram(postnet_output, ap, CONFIG):
    if CONFIG.model in ["Tacotron", "TacotronGST"]:
        wav = ap.inv_spectrogram(postnet_output.T)
    else:
        wav = ap.inv_mel_spectrogram(postnet_output.T)
    return wav


def id_to_torch(speaker_id):
    if speaker_id is not None:
        speaker_id = np.asarray(speaker_id)
        speaker_id = torch.from_numpy(speaker_id).unsqueeze(0)
    return speaker_id


def synthesis(model,
              text,
              CONFIG,
              use_cuda,
              ap,
              speaker_id=None,
              style_wav=None,
              truncated=False,
              enable_eos_bos_chars=False, #pylint: disable=unused-argument
              use_griffin_lim=True,
              do_trim_silence=True):
    """Synthesize voice for the given text.

        Args:
            model (TTS.models): model to synthesize.
            text (str): target text
            CONFIG (dict): config dictionary to be loaded from config.json.
            use_cuda (bool): enable cuda.
            ap (TTS.utils.audio.AudioProcessor): audio processor to process
                model outputs.
            speaker_id (int): id of speaker
            style_wav (str): Uses for style embedding of GST.
            truncated (bool): keep model states after inference. It can be used
                for continuous inference at long texts.
            enable_eos_bos_chars (bool): enable special chars for end of sentence and start of sentence.
            do_trim_silence (bool): trim silence after synthesis.
    """
    # GST processing
    style_mel = None
    #if CONFIG.model == "TacotronGST" and style_wav is not None:
    if style_wav is not None:
        style_mel = compute_style_mel( style_wav, ap, use_cuda)
        ref_cond=True	
    # preprocess the given text
    inputs = text_to_seqvec(text, CONFIG, use_cuda)
    speaker_id = id_to_torch(speaker_id)

    if speaker_id is not None and use_cuda:
        speaker_id = speaker_id.cuda()
    # synthesize voice
    decoder_output, postnet_output,postnet_output_noRef, alignments, stop_tokens = run_model(
        model, inputs, CONFIG, truncated, speaker_id, style_mel,ref_cond)

    # convert outputs to numpy
    postnet_output, decoder_output, alignment = parse_outputs(postnet_output, decoder_output, alignments)
    if ref_cond:
        postnet_output_noRef=postnet_output_noRef[0].data.cpu().numpy()

    print('>>>>>>>>>>>>>>>>>>>>3')
    # plot results
    wav = None
    if use_griffin_lim:
        wav = inv_spectrogram(postnet_output, ap, CONFIG)
        wav_noRef = inv_spectrogram(postnet_output_noRef, ap, CONFIG)
        # trim silence
        if do_trim_silence:
            wav = trim_silence(wav, ap)
            wav_noRef = trim_silence(wav_noRef, ap)
    return wav,wav_noRef, alignment, decoder_output, postnet_output,postnet_output_noRef, stop_tokens
